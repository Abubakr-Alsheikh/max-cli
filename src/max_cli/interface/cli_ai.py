import typer
import os
from max_cli.common.logger import console

# In a real scenario, you would import OpenAI client here

app = typer.Typer()


@app.command("ask")
def ask_ai(prompt: str):
    """
    Natural Language Interface: "max ai ask 'Compress the photos folder'"
    """
    console.print(f"[info]Thinking about:[/info] {prompt}")

    # 1. Pseudo-code for AI Logic:
    # response = openai.ChatCompletion.create(...)
    # command_to_run = response.choices[0].message.function_call

    # 2. Simulation for Demo:
    if "compress" in prompt.lower():
        console.print(
            "[bold green]AI Suggestion:[/bold green] Detected intent to compress."
        )
        console.print("Running: [bold]max images compress ./photos --quality 80[/bold]")
        # In the future: subprocess.run(["max", "compress", ...])
    elif "order" in prompt.lower():
        console.print(
            "[bold green]AI Suggestion:[/bold green] Detected intent to order files."
        )
        console.print("Running: [bold]max files order ./documents[/bold]")
    else:
        console.print(
            "[red]I'm not sure how to do that yet. Try 'compress' or 'order'.[/red]"
        )
