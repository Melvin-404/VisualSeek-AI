import time
import numpy as np
from sklearn.cluster import KMeans

def test_speed():
    # Generate mock 64x64 HSV pixels and mask weights
    pixels = np.random.randint(0, 255, (4096, 3)).astype(np.float32)
    weights = np.random.rand(4096).astype(np.float32)

    # Pre-warm KMeans
    kmeans = KMeans(n_clusters=3, n_init=1, max_iter=10, random_state=42)
    kmeans.fit(pixels[:100], sample_weight=weights[:100])

    times = []
    for _ in range(50):
        start = time.perf_counter()
        kmeans = KMeans(n_clusters=3, n_init=1, max_iter=10, random_state=42)
        kmeans.fit(pixels, sample_weight=weights)
        end = time.perf_counter()
        times.append((end - start) * 1000)

    print(f"Mean execution time over 50 runs: {np.mean(times):.3f} ms")
    print(f"Min execution time: {np.min(times):.3f} ms")
    print(f"Max execution time: {np.max(times):.3f} ms")

if __name__ == "__main__":
    test_speed()
