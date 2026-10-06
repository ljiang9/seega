#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Seega（塞加棋）——古埃及棋盘游戏。

规则（现代简化版）：
- 5x5 棋盘，双方各 12 子，中央格初始为空且为安全格。
- 布子阶段：双方轮流每次布 2 子，中央格不能布子。
- 走子阶段：每次把一枚自己的子正交走一格到空格。
- 吃子（custodian capture）：走子后，若敌子被夹在「刚走到的子」和
  另一枚己子之间（正交直线），则被吃。中央格上的子永不被吃。
  自己主动走进两枚敌子之间是安全的（不会被吃）。
- 胜负：吃光对方子者胜；轮到你走时无合法走法则判负。

只有 Python 标准库。
"""

import argparse
import random
import sys

SIZE = 5
EMPTY = 0
P0 = 1  # 先手（甲）
P1 = 2  # 后手（乙）
CENTER = (2, 2)  # 安全格：上面的子不会被吃，也不能布子
DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1)]
PIECES_PER_SIDE = 12
MAX_MOVES = 600  # 走子阶段上限，撞上限判和棋


def other(player):
    return P1 if player == P0 else P0


def in_bounds(r, c):
    return 0 <= r < SIZE and 0 <= c < SIZE


def capture_squares(board, player, tr, tc):
    """走子落到 (tr,tc) 后，被夹住的敌子坐标列表（纯函数，不改棋盘）。"""
    foe = other(player)
    caps = []
    for dr, dc in DIRS:
        nr, nc = tr + dr, tc + dc
        br, bc = nr + dr, nc + dc
        if (in_bounds(nr, nc) and in_bounds(br, bc)
                and board[nr][nc] == foe
                and board[br][bc] == player
                and (nr, nc) != CENTER):  # 安全格不被吃
            caps.append((nr, nc))
    return caps


class Seega:
    """可测试的 Seega 对局核心。"""

    def __init__(self):
        self.board = [[EMPTY] * SIZE for _ in range(SIZE)]
        self.phase = "place"          # place -> move
        self.to_place = {P0: PIECES_PER_SIDE, P1: PIECES_PER_SIDE}
        self.counts = {P0: PIECES_PER_SIDE, P1: PIECES_PER_SIDE}
        self.turn = P0
        self.n_moves = 0

    # ---------- 布子 ----------

    def legal_placements(self):
        return [(r, c) for r in range(SIZE) for c in range(SIZE)
                if self.board[r][c] == EMPTY and (r, c) != CENTER]

    def place(self, player, r, c):
        if self.phase != "place":
            raise ValueError("布子阶段已结束")
        if not in_bounds(r, c):
            raise ValueError(f"越界: {(r, c)}")
        if (r, c) == CENTER:
            raise ValueError("中央安全格不能布子")
        if self.board[r][c] != EMPTY:
            raise ValueError(f"格子已被占: {(r, c)}")
        if self.to_place[player] <= 0:
            raise ValueError("你的子已经布完了")
        self.board[r][c] = player
        self.to_place[player] -= 1
        if self.to_place[P0] == 0 and self.to_place[P1] == 0:
            self.phase = "move"

    # ---------- 走子 ----------

    def legal_moves(self, player):
        moves = []
        for r in range(SIZE):
            for c in range(SIZE):
                if self.board[r][c] != player:
                    continue
                for dr, dc in DIRS:
                    nr, nc = r + dr, c + dc
                    if in_bounds(nr, nc) and self.board[nr][nc] == EMPTY:
                        moves.append(((r, c), (nr, nc)))
        return moves

    def apply_move(self, player, move):
        """执行走子，返回本次吃掉的敌子坐标列表。非法走法抛 ValueError。"""
        if self.phase != "move":
            raise ValueError("还没到走子阶段")
        (fr, fc), (tr, tc) = move
        if not (in_bounds(fr, fc) and in_bounds(tr, tc)):
            raise ValueError(f"走法越界: {move}")
        if self.board[fr][fc] != player:
            raise ValueError("起点不是你的子")
        if self.board[tr][tc] != EMPTY:
            raise ValueError("落点被占")
        if abs(tr - fr) + abs(tc - fc) != 1:
            raise ValueError("只能正交走一格")
        self.board[fr][fc] = EMPTY
        self.board[tr][tc] = player
        self.n_moves += 1
        captured = capture_squares(self.board, player, tr, tc)
        for r, c in captured:
            self.board[r][c] = EMPTY
            self.counts[other(player)] -= 1
        return captured

    # ---------- 胜负 ----------

    def winner(self):
        if self.counts[P0] == 0:
            return P1
        if self.counts[P1] == 0:
            return P0
        return None


# ---------- 渲染 ----------

GLYPH = {EMPTY: "·", P0: "●", P1: "○"}


def render(game):
    lines = ["   " + " ".join(str(c + 1) for c in range(SIZE))]
    for r in range(SIZE):
        row = []
        for c in range(SIZE):
            if (r, c) == CENTER and game.board[r][c] == EMPTY:
                row.append("☆")
            else:
                row.append(GLYPH[game.board[r][c]])
        lines.append(f"{r + 1}  " + " ".join(row))
    return "\n".join(lines)


# ---------- AI ----------

def _min_enemy_dist(board, player, tr, tc):
    foe = other(player)
    best = None
    for r in range(SIZE):
        for c in range(SIZE):
            if board[r][c] == foe:
                d = abs(tr - r) + abs(tc - c)
                if best is None or d < best:
                    best = d
    return best if best is not None else 0


def ai_choose(game, player, rng):
    """贪心 AI：布子随机；走子优先吃子，其次贴近敌子。"""
    if game.phase == "place":
        spots = game.legal_placements()
        return ("place", rng.choice(spots)) if spots else None
    moves = game.legal_moves(player)
    if not moves:
        return None
    scored = []
    for mv in moves:
        (_, _), (tr, tc) = mv
        caps = len(capture_squares_after(game, player, mv))
        closeness = -_min_enemy_dist_after(game, player, mv, tr, tc)
        scored.append((caps, closeness, rng.random(), mv))
    scored.sort(reverse=True)
    return ("move", scored[0][3])


def capture_squares_after(game, player, move):
    (fr, fc), (tr, tc) = move
    b = [row[:] for row in game.board]
    b[fr][fc] = EMPTY
    b[tr][tc] = player
    return capture_squares(b, player, tr, tc)


def _min_enemy_dist_after(game, player, move, tr, tc):
    (fr, fc), _ = move
    b = [row[:] for row in game.board]
    b[fr][fc] = EMPTY
    b[tr][tc] = player
    return _min_enemy_dist(b, player, tr, tc)


# ---------- 自动对局 ----------

def play_one_game(rng, verbose=False):
    g = Seega()
    turn = P0
    # 布子阶段：双方轮流每次布 2 子
    while g.phase == "place":
        for _ in range(2):
            spots = g.legal_placements()
            if not spots:
                break
            r, c = rng.choice(spots)
            g.place(turn, r, c)
        turn = other(turn)
    # 走子阶段
    while g.n_moves < MAX_MOVES:
        choice = ai_choose(g, turn, rng)
        if choice is None:            # 无合法走法，判负
            return other(turn), g
        _, mv = choice
        caps = g.apply_move(turn, mv)
        if verbose:
            (fr, fc), (tr, tc) = mv
            print(f"{'甲' if turn == P0 else '乙'}: "
                  f"({fr + 1},{fc + 1})->({tr + 1},{tc + 1})"
                  + (f" 吃{caps}" if caps else ""))
        w = g.winner()
        if w is not None:
            return w, g
        turn = other(turn)
    return None, g  # 和棋


def play_auto(games=10, seed=42, verbose=False):
    rng = random.Random(seed)
    w0 = w1 = draws = 0
    for i in range(games):
        result, _ = play_one_game(rng, verbose=verbose)
        if result == P0:
            w0 += 1
            tag = "甲胜"
        elif result == P1:
            w1 += 1
            tag = "乙胜"
        else:
            draws += 1
            tag = "和棋"
        if not verbose:
            print(f"第 {i + 1}/{games} 局：{tag}")
    print(f"总计：甲胜 {w0}，乙胜 {w1}，和棋 {draws}")
    return w0, w1, draws


# ---------- 人机交互 ----------

def parse_coord(s):
    parts = s.strip().split()
    if len(parts) != 2:
        raise ValueError("请输入两个数字，如：2 3")
    r, c = int(parts[0]) - 1, int(parts[1]) - 1
    if not in_bounds(r, c):
        raise ValueError("坐标越界（行列均为 1-5）")
    return r, c


def play_interactive(seed=None):
    rng = random.Random(seed)
    g = Seega()
    human = P0
    print("Seega 塞加棋：你是 ●（甲，先手），AI 是 ○（乙）。")
    print("布子：输入 行 列（如 2 3），每轮布 2 子；"
          "走子：输入 起行 起列 落行 落列（如 2 3 2 4）。")
    print("输入 q 退出。☆ 为中央安全格。\n")
    # 布子阶段：双方轮流每次布 2 子
    while g.phase == "place":
        print(render(g))
        print(f"布子阶段：甲剩 {g.to_place[P0]} / 乙剩 {g.to_place[P1]}")
        placed = 0
        while placed < 2 and g.phase == "place" and g.to_place[human] > 0:
            s = input("布子> ").strip()
            if s == "q":
                return
            try:
                r, c = parse_coord(s)
                g.place(human, r, c)
                placed += 1
            except ValueError as e:
                print("非法：", e)
        ai_spots = []
        for _ in range(2):
            spots = g.legal_placements()
            if not spots or g.to_place[P1] <= 0:
                break
            r, c = rng.choice(spots)
            g.place(P1, r, c)
            ai_spots.append((r + 1, c + 1))
        if ai_spots:
            print("AI 布子：", ai_spots)
    # 走子阶段
    while True:
        print(render(g))
        print(f"甲 {g.counts[P0]} 子 / 乙 {g.counts[P1]} 子（已走 {g.n_moves} 手）")
        if g.turn == human:
            if not g.legal_moves(human):
                print("你无棋可走，判负。")
                return
            s = input("走子> ").strip()
            if s == "q":
                return
            try:
                p = s.split()
                if len(p) != 4:
                    raise ValueError("请输入四个数字")
                fr, fc = int(p[0]) - 1, int(p[1]) - 1
                tr, tc = int(p[2]) - 1, int(p[3]) - 1
                caps = g.apply_move(human, ((fr, fc), (tr, tc)))
                if caps:
                    print("吃子！", [(r + 1, c + 1) for r, c in caps])
            except ValueError as e:
                print("非法：", e)
                continue
        else:
            choice = ai_choose(g, P1, rng)
            if choice is None:
                print("AI 无棋可走，你赢了！")
                return
            _, mv = choice
            caps = g.apply_move(P1, mv)
            (fr, fc), (tr, tc) = mv
            print(f"AI 走子：({fr + 1},{fc + 1})->({tr + 1},{tc + 1})"
                  + (" 吃子！" if caps else ""))
        w = g.winner()
        if w is not None:
            print(render(g))
            print("你赢了！" if w == human else "AI 赢了。")
            return
        if g.n_moves >= MAX_MOVES:
            print("达到手数上限，和棋。")
            return
        g.turn = other(g.turn)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Seega 塞加棋（古埃及 5x5 棋盘游戏）")
    ap.add_argument("--auto", action="store_true", help="AI 对 AI 自动演示")
    ap.add_argument("--games", type=int, default=10, help="自动演示局数")
    ap.add_argument("--seed", type=int, default=42, help="随机种子")
    ap.add_argument("--verbose", action="store_true", help="自动演示打印每手")
    args = ap.parse_args(argv)
    if args.auto:
        play_auto(games=args.games, seed=args.seed, verbose=args.verbose)
    else:
        if not sys.stdin.isatty():
            print("交互模式需要终端；无头演示请用 --auto", file=sys.stderr)
            sys.exit(2)
        play_interactive(seed=args.seed)


if __name__ == "__main__":
    main()
