import time
import numpy as np
from sklearn.cluster import KMeans

def test_speed():
    pixels = np.random.randint(0, 255, (256, 3)).astype(np.float32)
    weights = np.random.rand(256).astype(np.float32)

    # Pre-warm KMeans
    kmeans = KMeans(n_clusters=3, n_init=1, max_iter=3, tol=1e-2, random_state=42)
    kmeans.fit(pixels[:100], sample_weight=weights[:100])

    times = []
    for _ in range(50):
        start = time.perf_counter()
        kmeans = KMeans(n_clusters=3, n_init=1, max_iter=3, tol=1e-2, random_state=42)
        kmeans.fit(pixels, sample_weight=weights)
        end = time.perf_counter()
        times.append((end - start) * 1000)

    print(f"Subsampled 16x16 Mean execution time over 50 runs: {np.mean(times):.3f} ms")

if __name__ == "__main__":
    test_speed()
