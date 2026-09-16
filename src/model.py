"""LSTM Autoencoder: encoder compresses a window, decoder reconstructs it."""

from __future__ import annotations

import tensorflow as tf
from tensorflow.keras import layers, models

from src.config import DECODER_UNITS, ENCODER_UNITS, LEARNING_RATE


def build_lstm_autoencoder(window_length: int, n_features: int) -> tf.keras.Model:
    inputs = layers.Input(shape=(window_length, n_features), name="window")

    # Encoder: stacked LSTMs, ending in one bottleneck vector.
    x = inputs
    for i, units in enumerate(ENCODER_UNITS):
        return_sequences = i < len(ENCODER_UNITS) - 1
        x = layers.LSTM(units, return_sequences=return_sequences, name=f"encoder_lstm_{i}")(x)

    bottleneck = x
    x = layers.RepeatVector(window_length, name="repeat_bottleneck")(bottleneck)

    # Decoder: stacked LSTMs, unrolling back into a full sequence.
    for i, units in enumerate(DECODER_UNITS):
        x = layers.LSTM(units, return_sequences=True, name=f"decoder_lstm_{i}")(x)

    outputs = layers.TimeDistributed(layers.Dense(n_features), name="reconstruction")(x)

    autoencoder = models.Model(inputs, outputs, name="lstm_autoencoder")
    autoencoder.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=LEARNING_RATE),
        loss="mse",
    )
    return autoencoder
