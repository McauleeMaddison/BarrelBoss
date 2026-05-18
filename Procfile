web: gunicorn taptrack.wsgi:application --bind 0.0.0.0:$PORT --log-file - --access-logfile - --timeout 120 --graceful-timeout 30 --keep-alive 75 --worker-tmp-dir /dev/shm
