import typer

app = typer.Typer(name="dotagent", help="Autonomous coding agent with a sandboxed workspace.")


@app.command()
def version() -> None:
    """Print the installed dotagent version."""
    typer.echo("dotagent 0.1.0")


if __name__ == "__main__":
    app()
