import numpy as np
from sequences import make_windows

FOLDS = [(range(2015, 2019), [2019]), (range(2015, 2021), [2021, 2022]), (range(2015, 2023), [2023])]
X, meta = make_windows()
print(X.shape, "missing values", int(np.isnan(X).sum()))
for train_years, val_years in FOLDS:
    for name, yrs in [("train", list(train_years)), ("val", val_years)]:
        m = meta[meta["year"].isin(yrs)]
        print(name, val_years[0], m["label_status"].value_counts().to_dict())