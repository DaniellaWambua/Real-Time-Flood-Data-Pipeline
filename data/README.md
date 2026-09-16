# Data

`raw/Dataset.csv` and `raw/Dataset_labels_v4.csv` each hold daily records for four catchments
(Mathare, Motoine, Nairobi River, Ngong) from 2010 to 2025, with hydrometeorological features
and a `flood_event` label already merged in. `Dataset_labels_v4.csv` is the more recent,
verified label set and is the one used for training.

Class balance is heavily skewed towards `flood_event = 0` (roughly 0.9 percent positive),
which is why an LSTM Autoencoder (trained on normal sequences, flagging deviations) was
chosen over a supervised classifier.
