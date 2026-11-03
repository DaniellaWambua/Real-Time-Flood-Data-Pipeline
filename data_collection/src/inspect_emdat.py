import glob
import pandas as pd

path = glob.glob("data_collection/data/01_flood_labels/raw/emdat/*.xlsx")[0]
df = pd.read_excel(path)

print(df.shape)
print(list(df.columns))
print(df.head(3).T)