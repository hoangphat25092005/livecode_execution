from app import create_app
import os

app = create_app()

if __name__ == "__main__":
    # Must bind to 0.0.0.0 for Docker
    app.run(
        host='0.0.0.0',  # Listen on all interfaces
        port=5000,
        debug=os.getenv('DEBUG', 'False').lower() == 'true'
    )

