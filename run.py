import os

from app import create_app
from config import DevelopmentConfig, ProductionConfig

# Published / hosted: use production config when the platform sets PORT or DATABASE_URL
_use_prod = bool(os.environ.get("PORT") or os.environ.get("DATABASE_URL") or os.environ.get("CURSOR_APP_ID"))
app = create_app(ProductionConfig if _use_prod else DevelopmentConfig)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    # 0.0.0.0 so Cursor / remote port forwarding can reach the app
    app.run(debug=not _use_prod, host="0.0.0.0", port=port)
