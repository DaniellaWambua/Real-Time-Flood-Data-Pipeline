"""LSTM Autoencoder: encoder compresses a window, decoder reconstructs it."""

from __future__ import annotations

import tensorflow as tf
from tensorflow.keras import layers, models

from src.config import AUTOENCODER_DROPOUT, DECODER_UNITS, ENCODER_UNITS, LEARNING_RATE


def build_lstm_autoencoder(window_length: int, n_features: int, dropout: float = AUTOENCODER_DROPOUT) -> tf.keras.Model:
    """Dropout added 2026-10-27 (Phase 12 finalisation): targets the documented
    drift problem (the model fits 2010-2022 "normal" too tightly, so 2024-2025
    looks artificially anomalous even on ordinary days) directly, rather than
    recalibrating the threshold after training, as every prior scheme did."""
    inputs = layers.Input(shape=(window_length, n_features), name="window")

    # Encoder: stacked LSTMs, ending in one bottleneck vector.
    x = inputs
    for i, units in enumerate(ENCODER_UNITS):
        return_sequences = i < len(ENCODER_UNITS) - 1
        x = layers.LSTM(units, return_sequences=return_sequences, name=f"encoder_lstm_{i}")(x)
        x = layers.Dropout(dropout, name=f"encoder_dropout_{i}")(x)

    bottleneck = x
    x = layers.RepeatVector(window_length, name="repeat_bottleneck")(bottleneck)

    # Decoder: stacked LSTMs, unrolling back into a full sequence.
    for i, units in enumerate(DECODER_UNITS):
        x = layers.LSTM(units, return_sequences=True, name=f"decoder_lstm_{i}")(x)
        x = layers.Dropout(dropout, name=f"decoder_dropout_{i}")(x)

    outputs = layers.TimeDistributed(layers.Dense(n_features), name="reconstruction")(x)

    autoencoder = models.Model(inputs, outputs, name="lstm_autoencoder")
    autoencoder.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=LEARNING_RATE),
        loss="mse",
    )
    return autoencoder


def build_lstm_classifier(window_length: int, n_features: int, units: int = 32,
                          dropout: float = 0.3) -> tf.keras.Model:
    """Supervised LSTM: reads the whole window, outputs P(flood on the last day).

    Unlike the autoencoder above, this learns directly from labelled flood
    days, so it is told what a flood looks like rather than only what
    "normal" looks like.
    """
    inputs = layers.Input(shape=(window_length, n_features), name="window")
    x = layers.LSTM(units, name="lstm")(inputs)
    x = layers.Dropout(dropout)(x)
    x = layers.Dense(16, activation="relu")(x)
    outputs = layers.Dense(1, activation="sigmoid", name="flood_probability")(x)

    model = models.Model(inputs, outputs, name="lstm_classifier")
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=LEARNING_RATE),
                  loss="binary_crossentropy")
    return model


def build_cnn_classifier(window_length: int, n_features: int, filters: int = 32,
                         kernel_size: int = 3, dropout: float = 0.3) -> tf.keras.Model:
    """1D convolutional network: slides short filters along the window
    looking for local patterns (e.g. a sharp three-day rise), then pools."""
    inputs = layers.Input(shape=(window_length, n_features), name="window")
    x = layers.Conv1D(filters, kernel_size, activation="relu", padding="causal")(inputs)
    x = layers.Conv1D(filters, kernel_size, activation="relu", padding="causal")(x)
    x = layers.GlobalMaxPooling1D()(x)
    x = layers.Dropout(dropout)(x)
    x = layers.Dense(16, activation="relu")(x)
    outputs = layers.Dense(1, activation="sigmoid", name="flood_probability")(x)

    model = models.Model(inputs, outputs, name="cnn_classifier")
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=LEARNING_RATE),
                  loss="binary_crossentropy")
    return model
