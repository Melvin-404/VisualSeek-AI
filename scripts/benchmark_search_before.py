import asyncio
import os
import sys
import time
import json
from pathlib import Path
# tabulate removed to use built-in formatting

# Add apps/api and packages/ai-pipeline/src to path
root = Path(__file__).resolve().parents[1]
sys.path.append(str(root / "apps" / "api"))
sys.path.append(str(root / "packages" / "ai-pipeline" / "src"))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(root / "apps" / "api" / ".env")

os.environ["API_ENV"] = "development"

from app.services.vector_search import VectorSearchService

# Define the 30 queries and their ground truth matches (mock database entity IDs)
TEST_QUERIES = {
    "colour": [
        ("grey car", ["mock-parking-2"]),
        ("red shirt", []), # No exact matching record
        ("blue vehicle", ["mock-roadway-2", "mock-dock-1"]),
        ("yellow taxi", []), # No exact matching record
        ("black SUV", []), # No exact matching record
        ("white sedan", []), # No exact matching record
        ("silver automobile", ["mock-dock-2"]),
        ("green jacket", ["mock-parking-2"]),
        ("orange top", []),
        ("purple motorcycle", [])
    ],
    "attribute": [
        ("person carrying umbrella", []), # No umbrella in mock DB
        ("man with backpack", ["mock-lobby-1"]),
        ("woman in dress", ["mock-lobby-3"]),
        ("person in hard hat", []),
        ("receptionist with laptop", ["mock-lobby-2"]),
        ("person holding phone", ["mock-lobby-3"]),
        ("security guard with cup", ["mock-lobby-4"]),
        ("rider with helmet", ["mock-roadway-2"]),
        ("person in safety vest", ["mock-dock-4"]),
        ("worker operating forklift", ["mock-dock-4"])
    ],
    "temporal_cross_camera": [
        ("same person seen near Parking Lot A and later near lobby", []),
        ("vehicles that appeared between 6 PM and 8 PM", []),
        ("same car spotted across three cameras", []),
        ("person who entered lobby between 10 AM and 11 AM", []),
        ("track the delivery rider trajectory", []),
        ("long dwell times at loading dock", []),
        ("vehicles seen in parking lot after 10 PM", []),
        ("same individual seen near lobby and loading dock", []),
        ("dwell time of forklift near bay 2", []),
        ("vehicles entering parking lot between 12 PM and 2 PM", [])
    ]
}

async def run_benchmark():
    service = VectorSearchService()
    print("Initialising VectorSearchService and pre-warming OpenCLIP model...")
    # Trigger one dummy search to warm up models and caches
    await service.search("warmup", limit=1)
    
    results_report = {}
    summary_data = []

    for category, queries in TEST_QUERIES.items():
        print(f"\nBenchmarking Category: {category}...")
        category_metrics = {
            "p@1": [],
            "p@5": [],
            "mrr": [],
            "latency": []
        }
        category_results = []
        
        for query_text, ground_truth in queries:
            start_time = time.perf_counter()
            try:
                search_res = await service.search(query_text=query_text, limit=5)
                latency_ms = (time.perf_counter() - start_time) * 1000.0
            except Exception as e:
                print(f"  Error querying '{query_text}': {e}")
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                search_res = {"results": []}
            
            hits = search_res.get("results", [])
            returned_ids = [hit.get("id") for hit in hits]
            
            # Compute metrics
            # P@1
            p1 = 0.0
            if returned_ids and ground_truth and returned_ids[0] in ground_truth:
                p1 = 1.0
            
            # P@5 (fraction of top 5 returned that are correct)
            p5 = 0.0
            correct_count = 0
            for r_id in returned_ids:
                if ground_truth and r_id in ground_truth:
                    correct_count += 1
            if ground_truth:
                p5 = correct_count / 5.0
            
            # MRR
            mrr = 0.0
            for rank, r_id in enumerate(returned_ids, start=1):
                if ground_truth and r_id in ground_truth:
                    mrr = 1.0 / rank
                    break
            
            category_metrics["p@1"].append(p1)
            category_metrics["p@5"].append(p5)
            category_metrics["mrr"].append(mrr)
            category_metrics["latency"].append(latency_ms)
            
            category_results.append({
                "query": query_text,
                "latency_ms": round(latency_ms, 2),
                "returned_ids": returned_ids,
                "ground_truth": ground_truth,
                "p@1": p1,
                "p@5": p5,
                "mrr": mrr
            })
            print(f"  Query: '{query_text}' | Latency: {latency_ms:.2f}ms | MRR: {mrr:.2f}")

        # Aggregate category results
        avg_p1 = sum(category_metrics["p@1"]) / len(queries)
        avg_p5 = sum(category_metrics["p@5"]) / len(queries)
        avg_mrr = sum(category_metrics["mrr"]) / len(queries)
        avg_latency = sum(category_metrics["latency"]) / len(queries)
        
        results_report[category] = {
            "queries": category_results,
            "metrics": {
                "precision_at_1": round(avg_p1, 4),
                "precision_at_5": round(avg_p5, 4),
                "mean_reciprocal_rank": round(avg_mrr, 4),
                "mean_latency_ms": round(avg_latency, 2)
            }
        }
        
        summary_data.append([
            category.upper(),
            f"{avg_p1 * 100:.1f}%",
            f"{avg_p5 * 100:.1f}%",
            f"{avg_mrr:.4f}",
            f"{avg_latency:.2f} ms"
        ])

    # Save JSON report
    report_dir = root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "baseline_search_accuracy.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results_report, f, indent=2)
    print(f"\nSaved baseline accuracy report to: {report_path}")

    # Print summary table
    print("\n" + "="*80)
    print("BASELINE VISUAL SEARCH ACCURACY SUMMARY")
    print("="*80)
    print(f"{'Category':<25} | {'Precision@1':<12} | {'Precision@5':<12} | {'MRR':<10} | {'Mean Latency':<15}")
    print("-"*80)
    for row in summary_data:
        print(f"{row[0]:<25} | {row[1]:<12} | {row[2]:<12} | {row[3]:<10} | {row[4]:<15}")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(run_benchmark())
