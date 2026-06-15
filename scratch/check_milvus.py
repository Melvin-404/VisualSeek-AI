from pymilvus import connections, utility, Collection

def main():
    host = "localhost"
    port = "19530"

    print("Connecting to Milvus...")
    try:
        connections.connect(host=host, port=port)
        print("Connected!")
        collections = utility.list_collections()
        print("Listing collections:")
        print(collections)

        for col_name in collections:
            try:
                col = Collection(col_name)
                # Load collection is required to get entities count in some versions
                col.load()
                num_entities = col.num_entities
                print(f"Collection: {col_name} | Num Entities: {num_entities}")
            except Exception as e:
                print(f"Failed to read collection {col_name}: {str(e)}")
    except Exception as e:
        print(f"Failed to connect to Milvus: {e}")

if __name__ == "__main__":
    main()
