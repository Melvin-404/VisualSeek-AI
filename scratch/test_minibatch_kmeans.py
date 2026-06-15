import time
import numpy as np
from sklearn.cluster import MiniBatchKMeans

def test_speed():
    pixels = np.random.randint(0, 255, (1024, 3)).astype(np.float32)
    weights = np.random.rand(1024).astype(np.float32)

    # Pre-warm MiniBatchKMeans
    kmeans = MiniBatchKMeans(n_clusters=3, n_init=1, max_iter=10, random_state=42)
    kmeans.fit(pixels[:100], sample_weight=weights[:100])

    times = []
    for _ in range(50):
        start = time.perf_counter()
        kmeans = MiniBatchKMeans(n_clusters=3, n_init=1, max_iter=10, batch_size=100, random_state=42)
        kmeans.fit(pixels, sample_weight=weights)
        end = time.perf_counter()
        times.append((end - start) * 1000)

    print(f"MiniBatchKMeans Mean execution time over 50 runs: {np.mean(times):.3f} ms")

if __name__ == "__main__":
    test_speed()
