from rich.panel import Panel
from rich.console import Group
from rich import box
from getkey import getkey, keys
import sys

refresh_always = False

def select_from(options, prompt, console, rest=None):
    global refresh_always
    selected = 0

    # for opt in options:

    if not refresh_always:
        console.print(rest)

    while True:
        display = []

        for opt in options:
            if opt is options[selected]:
                display.append("[bold](*) " + opt + "[/]")
            else:
                display.append("[dim]( ) " + opt + "[/]")

        if refresh_always:
            console.clear()
            if rest:
                console.print(Group(rest, Panel(Group(*display), box=box.HEAVY, title=prompt)))
            else:
                console.print(Panel(Group(*display), box=box.HEAVY, title=prompt))
        else:
            if rest:
                size = len(console.render_lines(rest))
            else:
                size = 0
            console.print("\n"*size, Panel(Group(*display), box=box.HEAVY, title=prompt), end="")

        try:
            char = getkey()
        except KeyboardInterrupt:
            sys.exit(1)

        if char == keys.UP:
            selected -= 1
        elif char == keys.DOWN:
            selected += 1
        elif char == keys.ENTER:
            break

        selected %= len(options)

    return selected
