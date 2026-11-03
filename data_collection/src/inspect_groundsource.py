import glob
import pyarrow.parquet as pq

path = glob.glob("data_collection/data/01_flood_labels/raw/groundsource/*.parquet")[0]
pf = pq.ParquetFile(path)

print(pf.metadata.num_rows, "rows", pf.metadata.num_row_groups, "row groups")
print(pf.schema_arrow)

first = pf.read_row_group(0).slice(0, 3).to_pandas()
print(first.T)