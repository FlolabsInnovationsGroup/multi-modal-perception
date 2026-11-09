const ports = [5173, 5174, 5175];

for (const port of ports) {
  try {
    const res = await fetch(`http://localhost:${port}/api/health`, {
      signal: AbortSignal.timeout(2000),
    });
    const data = await res.json();
    console.log(`port ${port}:`, JSON.stringify(data));
  } catch {
    console.log(`port ${port}: not running`);
  }
}
