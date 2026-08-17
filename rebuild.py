import sys
sys.path.append('python')
from data_generator import run_data_generation, MultiFailureConfig
import etl
import data_generator_oee
import os
import sqlite3

print('1. Running Data Generation')
cfg = MultiFailureConfig(window_days=365)
run_data_generation(cfg, skip_plots=True)

print('\n2. Running ETL Pipeline')
if os.path.exists('data/manufacturing.db'):
    os.remove('data/manufacturing.db')
etl.run_etl_pipeline('data/processed', 'data/manufacturing.db', validate_only=False)

print('\n3. Applying Indexes')
c = sqlite3.connect('data/manufacturing.db')
c.execute('PRAGMA foreign_keys=ON;')
with open('sql/schema/indexes.sql', 'r') as f:
    c.executescript(f.read())
c.close()

print('\n4. Running OEE Generation')
data_generator_oee.run('data/manufacturing.db')
print('DONE')
