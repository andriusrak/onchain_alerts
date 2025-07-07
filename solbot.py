import subprocess

# Define the paths to your Python scripts
script1 = "soldex_scraper.py"
script2 = "signals_volume2.py"
script3 = "discord_alerts.py"

# Launch the scripts using subprocess.Popen
processes = []
for script in [script1, script2, script3]:
    processes.append(subprocess.Popen(["python", script]))

# Wait for all processes to complete
for process in processes:
    process.wait()

print("All scripts have finished execution.")