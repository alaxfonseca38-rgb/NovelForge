from __future__ import annotations

import typer

app = typer.Typer(help="NovelForge")

@app.command()
def info():
    print("NovelForge web edition. Use streamlit_app.py to start the interface.")

if __name__ == "__main__":
    app()
