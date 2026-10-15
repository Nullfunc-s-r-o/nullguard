# Docker Playground

This directory provides a safe, sandboxed environment to test NullGuard via Docker without touching your real system logs!

## How to use

1. Start the container (it builds from the main source code):
   ```bash
   docker-compose up -d --build
   ```

2. Open the NullGuard UI directly inside the running container:
   ```bash
   docker exec -it nullguard_test nullguard ui
   ```
   *(You should immediately see your host machine's CPU/RAM metrics populated at the top!)*

3. Open a second terminal on your host machine and inject a fake error into the mock log file:
   ```bash
   echo "CRITICAL: Database connection completely lost" >> mock_syslog.log
   ```

4. Watch the UI! You will instantly see the incident card pop up, proving the C++ engine is safely tailing the file.

When you're done, simply hit `q` in the UI and run `docker-compose down`.
