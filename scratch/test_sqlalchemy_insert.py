import sys
from app.models.base import Base
import app.models.schema_models # Make sure models are loaded

def main():
    print("Metadata sorted tables:")
    for table in Base.metadata.sorted_tables:
        print(f"  - {table.name}")
        
    print("\nCamera foreign keys:")
    camera_table = Base.metadata.tables["cameras"]
    for fk in camera_table.foreign_keys:
        print(f"  - Parent: {fk.parent}, Target: {fk.target_fullname}, Column: {fk.column}")

if __name__ == "__main__":
    main()
