from enum import Enum, auto
from functools import reduce
import os
import sys
import random
from graphics import select_from

from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.table import Table, Column
from rich.columns import Columns
from rich import box
from rich.rule import Rule
from rich.layout import Layout
from rich.console import Group, Console
from rich.prompt import Prompt, Confirm
from rich.align import Align
from rich import print
from rich.theme import Theme

log = []
turn = 0

def output(message):
    global log, turn
    log.append("Turn {}: {}".format(turn, message))

display_len = 45

class Affinity(Enum):
    NONE = 0
    WATER = auto() # 2x to FIRE, 0.5x to PLANT, 0x to ELECTRIC
    GHOST = auto() # 2x to ELECTRIC, 0.5x to WATER, 0.5x to GHOST
    FIRE = auto() # 2x to GHOST, 2x PLANT, 0x WATER, 0x ROCK
    ELECTRIC = auto() # 3x to WATER, 0x FIRE
    PLANT = auto() # 0.5x to ELECTRIC, 2x ROCK
    ROCK = auto() # 2x GHOST

    def multiplier(self, other):
        return {
            Affinity.NONE: {},
            Affinity.WATER: { Affinity.FIRE: 2, Affinity.PLANT: 0.5, Affinity.ELECTRIC: 0 },
            Affinity.GHOST: { Affinity.ELECTRIC: 2, Affinity.WATER: 0.5, Affinity.GHOST: 0.5 },
            Affinity.FIRE: { Affinity.GHOST: 2, Affinity.PLANT: 2, Affinity.WATER: 0, Affinity.ROCK: 0 },
            Affinity.ELECTRIC: { Affinity.WATER: 3, Affinity.FIRE: 0 },
            Affinity.PLANT: { Affinity.ELECTRIC: 0.5, Affinity.ROCK: 2 },
            Affinity.ROCK: { Affinity.GHOST: 2 },
        }.get(self).get(other, 1)

    def color(self):
        return {
            Affinity.NONE: 'white',
            Affinity.WATER: 'blue',
            Affinity.GHOST: 'magenta',
            Affinity.FIRE: 'red',
            Affinity.ELECTRIC: 'yellow',
            Affinity.PLANT: 'green',
            Affinity.ROCK: 'brown',
        }.get(self)

    def __str__(self):
        return {
            Affinity.NONE: 'None',
            Affinity.WATER: 'Water',
            Affinity.GHOST: 'Ghost',
            Affinity.FIRE: 'Fire',
            Affinity.ELECTRIC: 'Electric',
            Affinity.PLANT: 'Plant',
            Affinity.ROCK: 'Rock',
        }.get(self)

class Target(Enum):
    TEAM = auto()
    ENEMY = auto()
    SELF = auto()
    NONE = auto()

class Move:
    def colored(self, name):
        return "[{}]{}[/]".format(self.affinity.color(), name)

class Damage(Move):
    def __init__(self, cost, damage, affinity):
        self.target = Target.ENEMY

        self.cost = cost
        self.damage = damage
        self.affinity = affinity

    def affect(self):
        return "Deals [red]{} damage[/]".format(self.damage)

    def apply(self, monster):
        mul = 1

        for affinity in monster.affinities:
            mul *= self.affinity.multiplier(affinity)

        damage = max(self.damage - monster.bubble, 0)
        monster.bubble -= self.damage
        monster.bubble = max(monster.bubble, 0)
        monster.health -= int(damage * mul)
        return "[red]dealing {} damage[/]".format(int(damage * mul))

class Heal(Move):
    def __init__(self, cost, health, affinity):
        self.target = Target.TEAM

        self.cost = cost
        self.health = health
        self.affinity = affinity

    def affect(self):
        return "Heal [green]{} health[/]".format(self.health)

    def apply(self, monster):
        monster.health += self.health
        monster.health = min(monster.health, monster.max_health)
        return "[green]healing {} health[/]".format(self.health)

class Block(Move):
    def __init__(self, cost, health, affinity):
        self.target = Target.SELF

        self.cost = cost
        self.health = health
        self.affinity = affinity

    def affect(self):
        return "Prevents the next [blue]{} damage[/]".format(self.health)

    def apply(self, monster):
        monster.apply_bubble(self.health)
        return "Prevented the next [red]{} damage[/]".format(self.health)

def ansioff(s):
    return ansilen(s) - len(s)

class Monster:
    def __init__(self, health, name, affinities, moves, energy=100, energy_regen=1):
        self.health = health
        self.max_health = health
        self.name = name
        self.energy = energy
        self.max_energy = self.energy
        self.moves = moves
        self.affinities = affinities
        self.energy_regen = energy_regen*20
        self.bubble = 0
        self.max_bubble = self.max_health

        stats_col = Column(width=8, justify="right")
        frac_text = TextColumn("[white]{task.completed}/{task.total}", table_column=stats_col, justify="right")

        self.health_bar = Progress(
                BarColumn(complete_style="green", finished_style="green", bar_width=1000),
                frac_text,
                expand=True,
            )

        self.health_task = self.health_bar.add_task("Health", total=self.max_health)
        self.health_bar.update(self.health_task, completed=self.health)

        self.bubble_bar = Progress(
                BarColumn(complete_style="blue", finished_style="blue", bar_width=1000),
                frac_text,
                expand=True,
            )

        self.bubble_task = self.bubble_bar.add_task("Bubble", total=self.max_bubble)
        self.bubble_bar.update(self.bubble_task, completed=self.bubble)

        self.energy_bar = Progress(
                BarColumn(complete_style="yellow", finished_style="yellow", bar_width=1000),
                frac_text,
                expand=True,
            )

        self.energy_task = self.energy_bar.add_task("Energy", total=self.max_energy)
        self.energy_bar.update(self.energy_task, completed=self.energy)

        data_table = Table(box=box.SIMPLE_HEAVY, show_header=False, expand=True)

        data_table.add_column("Name")
        data_table.add_column("Status", justify="right")

        data_table.add_row("Affinities", self.caffinities())
        data_table.add_row("Health", self.health_bar)
        data_table.add_row("Shield", self.bubble_bar)
        data_table.add_row("Energy", self.energy_bar)

        moves_table = Table(box=box.SIMPLE, expand=True)

        moves_table.add_column("Name", justify="left")
        moves_table.add_column("Action")
        moves_table.add_column("Cost", justify="right", style="yellow")

        for name, move in self.moves.items():
            moves_table.add_row(move.colored(name), move.affect(), str(move.cost) + "🗲")

        self.short_panel = Panel(
            data_table,
            title="[bold]" + self.name,
            box=box.HEAVY,
            expand=True,
        )

        self.panel = Panel(
            Group(data_table, moves_table),
            title="[bold]" + self.name,
            box=box.HEAVY,
            expand=True,
        )

    def use_move(self, name, other):
        if name == "Skip":
            output("{} skipped".format(self.name))
            return

        move = self.moves[name]

        target = { Target.TEAM : self, Target.ENEMY: other, Target.SELF : self }.get(move.target)

        self.energy -= move.cost
        # target.damage(move.damage, move.affinity)
        result = move.apply(target)
        output("{} used {} on {} {}".format(self.name, move.colored(name), target.name, result))

    def caffinities(self):
        return reduce(lambda x, y: x + ", " + y, map(lambda x: "[{}]{}".format(x.color(), x), self.affinities))

    def status(self, short=False, color="red"):
        self.health_bar.update(self.health_task, completed=self.health)
        self.bubble_bar.update(self.bubble_task, completed=self.bubble)
        self.energy_bar.update(self.energy_task, completed=self.energy)

        self.panel.border_style = color

        if not short:
            return self.panel
        else:
            return self.short_panel

    def useable_moves(self):
        return list(map(lambda x: x[0], filter(lambda x: x[1].cost <= self.energy, self.moves.items())))

    def regen(self):
        self.energy = min(self.energy + self.energy_regen, self.max_energy)

    def take_turn(self):
        self.regen()
        # self.bubble = int(self.bubble / 2)

    def apply_bubble(self, amount):
        self.bubble += amount

def columns_monsters(monsters):
    return Columns([x.status(short=True) for x in monsters], width=int(100/len(monsters)), equal=True, expand=True)

def single_player_input(me, enemy, live, rest):
    moves = ["Skip"] + me.useable_moves()
    colored_moves = ["Skip"] + list(map(lambda x: "{} : {}".format(me.moves[x].colored(x), me.moves[x].affect()), me.useable_moves()))

    return moves[select_from(colored_moves, "Choose a move", live, rest)]

def player_input(me, enemy, name, live, rest):
    moves = ["Skip"] + me.useable_moves()
    colored_moves = ["Skip"] + list(map(lambda x: "{} : {}".format(me.moves[x].colored(x), me.moves[x].affect()), me.useable_moves()))

    return moves[select_from(colored_moves, "Choose a move ({})".format(name), live, rest)]

def one_player_input(me, enemy, live, rest):
    return player_input(me, enemy, "[green]player one[/]", live, rest)

def two_player_input(me, enemy, live, rest):
    return player_input(me, enemy, "[red]player two[/]", live, rest)

def rando_input(enemy, me, live, rest):
    possible_moves = enemy.useable_moves()

    if len(possible_moves) < len(enemy.moves):
        possible_moves.append("Skip")
    idx = random.randrange(len(possible_moves))

    return possible_moves[idx]

def game(console, me, enemy, first_player_input=single_player_input, second_player_input=rando_input):
    global turn
    turn = 0
    active_monster = me
    inactive_monster = enemy

    while True:
        turn += 1
        active_monster.take_turn()

        console.clear()
        rest = Group(
                me.status(color="green"),
                enemy.status(),
                Panel('\n'.join(log[-15:]), box=box.HEAVY)
            )
        console.print(rest)

        if active_monster is me:
            action = first_player_input(
                    active_monster,
                    inactive_monster,
                    console,
                    rest
                )
            me.use_move(action, enemy)
        else:
            action = second_player_input(
                    active_monster,
                    inactive_monster,
                    console,
                    rest
                )
            enemy.use_move(action, me)

        if me.health <= 0:
            output("[red]Player two wins[/]")
            break
        if enemy.health <= 0:
            output("[green]Player one wins[/]")
            break

        active_monster, inactive_monster = inactive_monster, active_monster

    # console.clear()
    # console.print(Group(me.status(color="green"), enemy.status()))
    # console.print(Panel('\n'.join(log[-20:]), box=box.HEAVY))

def all_monsters():
    monsters = []

    monsters += [Monster(
            750,
            "Piki",
            [Affinity.ELECTRIC],
            {
                "Shock" : Damage(50, 150, Affinity.ELECTRIC),
                "Zap" : Damage(20, 100, Affinity.ELECTRIC),
                "Tail Whip" : Damage(20, 50, Affinity.NONE),
                "Electric Shield" : Block(15, 50, Affinity.ELECTRIC),
            }
        )]

    monsters += [Monster(
            1000,
            "WaterBoo",
            [Affinity.WATER, Affinity.GHOST],
            {
                "Splash" : Damage(20, 120, Affinity.WATER),
                "Frighten": Damage(40, 200, Affinity.GHOST),
                "Spook" : Damage(20, 75, Affinity.GHOST),
                "Watery Wave" : Block(10, 40, Affinity.WATER)
            }
        )]

    monsters += [Monster(
            1000,
            "Planty",
            [Affinity.PLANT],
            {
                "Leaf Slash" : Damage(20, 100, Affinity.PLANT),
                "Regrow" : Heal(40, 300, Affinity.PLANT),
                "Slap" : Damage(10, 60, Affinity.NONE),
                "Seed Spit" : Damage(50, 160, Affinity.PLANT),
            }
        )]

    # monsters += [Monster(
    #         750,
    #         "floopy",
    #         [Affinity.FIRE],
    #         {
    #             "Leaf Slash" : Damage(20, 100, Affinity.PLANT),
    #             "Regrow" : Heal(40, 300, Affinity.PLANT),
    #             "Slap" : Damage(10, 60, Affinity.NONE),
    #             "Seed Spit" : Damage(50, 160, Affinity.PLANT),
    #         }
    #     )]

    monsters += [Monster(
            1500,
            "BolderGuy",
            [Affinity.ROCK],
            {
                "Avalanche" : Damage(50, 120, Affinity.ROCK),
                "Earthquake" : Damage(100, 300, Affinity.ROCK),
                "Granite Skin" : Block(50, 500, Affinity.ROCK),
                "Fortify" : Block(5, 15, Affinity.ROCK),
            },
            energy=200,
            energy_regen=0.5,
        )]

    return monsters

def select_monster(monsters, live, rest):
    return monsters[select_from(
        list(map(lambda x: x.name, monsters)),
        "Choose a monster",
        live,
        rest
    )].name

if __name__ == "__main__":
    theme = Theme({
        "brown": "#9B7653"
    })

    console = Console(theme=theme)
    console.set_alt_screen(True)

    with Live(console=console, screen=True, auto_refresh=False) as live:
        console.clear()
        two_player = select_from(["[red]Single-player[/]", "[green]Multiplayer[/]"], "Mode?", console) == 1

        while True:
            console.clear()

            monsters = all_monsters()
            rest = Columns(
                    list(map(lambda x: x.status(color="white"), monsters)),
                    equal=True,
                    expand=True,
                    width=50,
                    column_first=True
                )

            console.print(rest)

            chosen_monster = select_monster(monsters, console, rest)
            for monster in monsters:
                if monster.name == chosen_monster:
                    monsters.remove(monster)
                    me = monster

            if two_player:
                console.clear()
                console.print(rest)

                chosen_monster = select_monster(monsters, console, rest)
                for monster in monsters:
                    if monster.name == chosen_monster:
                        monsters.remove(monster)
                        enemy = monster
            else:
                idx = random.randrange(len(monsters))
                enemy = monsters[idx]

            log = []
            if two_player:
                game(
                        console,
                        me,
                        enemy,
                        first_player_input=one_player_input,
                        second_player_input=two_player_input
                    )
            else:
                game(console, me, enemy)

            console.clear()

            rest = Group(
                me.status(color="green"),
                enemy.status(),
                Panel('\n'.join(log[-15:]), box=box.HEAVY)
            )
            console.print(rest)

            if select_from(
                    ["[red]No[/]", "[green]Yes[/]"],
                    "Play Again?",
                    console,
                    rest
                ) == 0:
                console.set_alt_screen(False)
                break
