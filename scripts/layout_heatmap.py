DESCRIPTION = """
Plot a heatmap of good step tunings for isomorphic note layouts.

Layouts are scored by the sum of the inverse Tenney height of intervals
within an integer limit approximated within an error limit, taking the
center pad as 1/1. Point values for each interval are scaled based on
the square of the absolute error of the best approximation, down to 0
at the error limit.

Computation may take a few minutes.
"""

from argparse import ArgumentParser
from dataclasses import dataclass
import shelve
from fractions import Fraction
from itertools import chain
from math import log, log2
from typing import Callable, Iterable

def exquis_vectors() -> list[tuple[int, int]]:
    def row(g1: int, g2: int) -> Iterable[tuple[int, int]]:
        length = 5 if (g1 + g2) % 2 == 0 else 6
        return ((g1 + 1 - i, g2 - 1 + i) for i in range(length))
    
    return list(chain(
        row(4, 1), row(3, 1), row(3, 0), row(2, 0), row(2, -1),
        row(1, -1),
        row(1, -2), row(0, -2), row(0, -3), row(-1, -3), row(-1, -4)
    ))

def exquis39_vectors() -> list[tuple[int, int]]:
    def row(g1: int, g2: int) -> Iterable[tuple[int, int]]:
        length = 3 if (g1 + g2) % 2 == 0 else 4
        return ((g1 - i, g2 + i) for i in range(length))
    
    return list(chain(
        row(4, 1), row(3, 1), row(3, 0), row(2, 0), row(2, -1),
        row(1, -1),
        row(1, -2), row(0, -2), row(0, -3), row(-1, -3), row(-1, -4)
    ))

@dataclass
class Controller:
    name: str
    x_step_name: str
    y_step_name: str
    vector_func: Callable

controllers = {
    'exquis': Controller('Exquis', 'Up-right', 'Up-left', exquis_vectors),
    'exquis39': Controller('Exquis 39-key', 'Up-right', 'Up-left', exquis39_vectors),
}

parser = ArgumentParser(description=DESCRIPTION)
parser.add_argument('--error-limit', type=float, default=15)
parser.add_argument('--integer-limit', type=int, default=16)
parser.add_argument('--cached', action='store_true')
parser.add_argument('controller', nargs='+', choices=controllers.keys())
args = parser.parse_args()

import plotly.express as px
from tqdm.contrib.concurrent import process_map

def integer_limit_intervals(limit: int) -> set[Fraction]:
    return set(Fraction(n, d)
               for n in range(1, limit+1)
               for d in range(1, limit+1))

def cents(r: Fraction) -> float:
    return 1200 * log(r) / log(2)

def tenney_height(r: Fraction) -> float:
    return log2(r.numerator * r.denominator)

step_range = list(range(args.error_limit, 702 + args.error_limit))
error_limit_squared = args.error_limit ** 2

# Since we're measuring from the center of the keyboard, intervals are
# symmetric with their inverses. So we can ignore all intervals < 1,
# and then just double the score to get the same result. We also ignore
# 1/1 since its inverse Tenney height is undefined.
rs = [r for r in integer_limit_intervals(args.integer_limit)
      if r > 1]

interval_cents = {r: cents(r) for r in rs}

def point_value(interval: Fraction, cents: float, best_approximation: float) -> float:
    error = abs(best_approximation - cents)
    # Divide 2 instead of 1 here to make up for ignoring intervals < 1.
    return 2 / tenney_height(interval) * max(0, 1 - error*error / error_limit_squared)

cache = {}
cache_path = 'scripts/layout_heatmap'

def closest(x: float, xs: list[float]) -> float:
    return min(xs, key=lambda y: abs(x - y))

def write_figure(controller: str, matrix: list[list[float]]):
    # Round the scores to reduce file size.
    matrix = [[round(x, 1) for x in row] for row in matrix]
    c = controllers[controller]
    title = f'LCJI approximation by {c.name} note layouts'
    labels = {
        'x': f'{c.x_step_name} step',
        'y': f'{c.y_step_name} step',
        'color': 'Score',
    }
    fig = px.imshow(matrix,
                    title=title,
                    labels=labels,
                    x=step_range,
                    y=step_range)
    # Use a fixed div_id to avoid VCS noise from UUID regeneration.
    fig.write_html(f'src/layout-heatmaps/{controller}.html',
                   include_plotlyjs='cdn',
                   div_id='figure')

def layout_score(vectors: list[tuple[int, int]], steps: tuple[float, float]) -> float:
    key = tuple(sorted(steps))
    if key not in cache:
        cents_values = [steps[0]*v[0] + steps[1]*v[1] for v in vectors]
        cache[key] = sum(point_value(r, c, closest(c, cents_values))
                        for r, c in interval_cents.items())
    return cache[key]

def score_row(args: tuple) -> list[float]:
    vectors, upleft = args
    return [layout_score(vectors, (upleft, upright)) for upright in step_range]

def generate(controller: str):
    print(f'Generating {controller} plot')
    vectors = controllers[controller].vector_func()

    if args.cached:
        with shelve.open(cache_path) as db:
            matrix = db[controller]
    else:
        matrix = process_map(score_row, [(vectors, upleft)
                                         for upleft in step_range])

    write_figure(controller, matrix)
    
    with shelve.open(cache_path) as db:
        db[controller] = matrix

def main():
    for controller in args.controller:
        generate(controller)

if __name__ == '__main__':
    main()