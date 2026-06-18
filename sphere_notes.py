"""
SphereNotes — A visual notes app inspired by Final Fantasy X Sphere Grid.
Requires: PyQt5
"""

import sys
import os
import math
import sqlite3
import json
import random
from typing import Optional, List, Tuple

def _app_dir() -> str:
    """Always returns the folder where the EXE (or .py script) lives."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QGraphicsScene, QGraphicsView,
    QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsTextItem,
    QGraphicsItem, QDialog, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QScrollArea, QWidget, QFrame,
    QGraphicsPixmapItem, QShortcut, QMessageBox, QSizePolicy,
    QGraphicsDropShadowEffect, QMenu, QAction, QInputDialog,
    QColorDialog, QGridLayout, QToolButton
)
from PyQt5.QtCore import (
    Qt, QRectF, QPointF, QTimer, pyqtSignal, QObject, QSize, QThread
)
from PyQt5.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QFontDatabase,
    QPainterPath, QRadialGradient, QLinearGradient, QPalette,
    QKeySequence, QPixmap, QIcon, QTransform, QPolygonF
)

DB_PATH = os.path.join(_app_dir(), "sphere_notes.db")

# ─────────────────────────────────────────────
#  COLORS
# ─────────────────────────────────────────────
BG_COLOR        = QColor("#07001a")
GRID_LINE       = QColor(60, 20, 120, 40)
NODE_DEFAULT    = QColor("#1a0040")
NODE_GLOW       = QColor("#6a00ff")
CONNECT_COLOR   = QColor(120, 75, 255, 120)
CONNECT_ACTIVE  = QColor(190, 150, 255, 210)
STAR_COLOR      = QColor(235, 220, 255, 190)
TEXT_COLOR      = QColor("#d4c8ff")
ACCENT          = QColor("#a060ff")
GOLD            = QColor("#ffe08a")
SYMBOL_COLORS   = [
    "#a060ff", "#00d4ff", "#ff60c0", "#60ffa0",
    "#ffaa30", "#ff4060", "#30d0ff", "#c0ff60",
    "#ff80ff", "#40ffcc", "#ffcc40", "#80a0ff",
]

# ─────────────────────────────────────────────
#  DATABASE
# ─────────────────────────────────────────────
class DB:
    def __init__(self, path: str = DB_PATH):
        self.conn = sqlite3.connect(path)
        self._init()

    def _init(self):
        c = self.conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                title   TEXT DEFAULT '',
                content TEXT DEFAULT '',
                symbol  INTEGER DEFAULT 0,
                color   TEXT DEFAULT '#a060ff',
                x       REAL DEFAULT 0,
                y       REAL DEFAULT 0,
                created TEXT DEFAULT (datetime('now')),
                updated TEXT DEFAULT (datetime('now'))
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS connections (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                src   INTEGER,
                dst   INTEGER,
                UNIQUE(src, dst)
            )
        """)
        self.conn.commit()

    def get_notes(self):
        c = self.conn.cursor()
        c.execute("SELECT id,title,content,symbol,color,x,y FROM notes ORDER BY id")
        return c.fetchall()

    def add_note(self, title="", content="", symbol=0, color="#a060ff", x=0.0, y=0.0):
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO notes (title,content,symbol,color,x,y) VALUES (?,?,?,?,?,?)",
            (title, content, symbol, color, x, y)
        )
        self.conn.commit()
        return c.lastrowid

    def update_note(self, nid, title, content, symbol, color):
        c = self.conn.cursor()
        c.execute(
            "UPDATE notes SET title=?,content=?,symbol=?,color=?,updated=datetime('now') WHERE id=?",
            (title, content, symbol, color, nid)
        )
        self.conn.commit()

    def update_pos(self, nid, x, y):
        c = self.conn.cursor()
        c.execute("UPDATE notes SET x=?,y=? WHERE id=?", (x, y, nid))
        self.conn.commit()

    def delete_note(self, nid):
        c = self.conn.cursor()
        c.execute("DELETE FROM notes WHERE id=?", (nid,))
        c.execute("DELETE FROM connections WHERE src=? OR dst=?", (nid, nid))
        self.conn.commit()

    def get_connections(self):
        c = self.conn.cursor()
        c.execute("SELECT src, dst FROM connections")
        return c.fetchall()

    def add_connection(self, src, dst):
        if src == dst:
            return
        a, b = min(src, dst), max(src, dst)
        c = self.conn.cursor()
        try:
            c.execute("INSERT INTO connections (src, dst) VALUES (?,?)", (a, b))
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass

    def remove_connection(self, src, dst):
        a, b = min(src, dst), max(src, dst)
        c = self.conn.cursor()
        c.execute("DELETE FROM connections WHERE src=? AND dst=?", (a, b))
        self.conn.commit()

    def has_connection(self, src, dst):
        a, b = min(src, dst), max(src, dst)
        c = self.conn.cursor()
        c.execute("SELECT 1 FROM connections WHERE src=? AND dst=?", (a, b))
        return c.fetchone() is not None


# ─────────────────────────────────────────────
#  SYMBOL PAINTER  (27  symbols)
# ─────────────────────────────────────────────
def _star_polygon(cx, cy, r, n, ratio=0.5):
    pts = []
    for i in range(n * 2):
        angle = math.pi / n * i - math.pi / 2
        rr = r if i % 2 == 0 else r * ratio
        pts.append(QPointF(cx + rr * math.cos(angle), cy + rr * math.sin(angle)))
    p = QPainterPath()
    p.moveTo(pts[0])
    for pt in pts[1:]:
        p.lineTo(pt)
    p.closeSubpath()
    return p

def _circle_path(cx, cy, r):
    p = QPainterPath()
    p.addEllipse(QPointF(cx, cy), r, r)
    return p

SYMBOLS = []

def _build_symbols():
    """Returns list of (name, draw_fn) where draw_fn(painter, cx, cy, r, color)."""
    s = []

    # 0 — Pentagram
    def draw_pentagram(painter, cx, cy, r, color):
        painter.setPen(QPen(color, r * 0.08, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        path = _star_polygon(cx, cy, r * 0.86, 5, 0.38)
        painter.drawPath(path)
    s.append(("Pentagram", draw_pentagram))

    # 1 — Eye of Providence
    def draw_eye(painter, cx, cy, r, color):
        # Triangle
        painter.setPen(QPen(color, r * 0.07, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        tri = QPainterPath()
        tri.moveTo(cx, cy - r * 0.82)
        tri.lineTo(cx - r * 0.72, cy + r * 0.5)
        tri.lineTo(cx + r * 0.72, cy + r * 0.5)
        tri.closeSubpath()
        painter.drawPath(tri)
        # Eye lens (mandorla)
        eye_cx, eye_cy = cx, cy - r * 0.1
        p = QPainterPath()
        p.moveTo(eye_cx - r * 0.38, eye_cy)
        p.quadTo(eye_cx, eye_cy - r * 0.24, eye_cx + r * 0.38, eye_cy)
        p.quadTo(eye_cx, eye_cy + r * 0.24, eye_cx - r * 0.38, eye_cy)
        painter.drawPath(p)
        # Pupil
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(eye_cx, eye_cy), r * 0.12, r * 0.12)
        # Rays from triangle top
        painter.setPen(QPen(color, r * 0.055))
        for da in (-0.32, 0, 0.32):
            a = -math.pi / 2 + da
            painter.drawLine(QPointF(cx + r * 0.82 * math.cos(a), cy + r * 0.82 * math.sin(a) - r * 0.82 + cy - cy),
                             QPointF(cx + r * 0.95 * math.cos(a), cy + r * 0.95 * math.sin(a) - r * 0.82 + cy - cy))
    s.append(("Eye of Providence", draw_eye))

    # 2 — Spiral (Archimedean)
    def draw_spiral(painter, cx, cy, r, color):
        painter.setPen(QPen(color, r * 0.07, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        p = QPainterPath()
        turns = 3.5
        steps = 280
        p.moveTo(cx, cy)
        for i in range(1, steps + 1):
            t = i / steps * turns * 2 * math.pi
            rr = r * 0.84 * (i / steps)
            p.lineTo(cx + rr * math.cos(t - math.pi / 2),
                     cy + rr * math.sin(t - math.pi / 2))
        painter.drawPath(p)
    s.append(("Spiral", draw_spiral))

    # 3 — Hexagram (Star of David)
    def draw_hexagram(painter, cx, cy, r, color):
        painter.setPen(QPen(color, r * 0.08, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        for rot in (0, math.pi / 3):
            tri = QPainterPath()
            pts = [QPointF(cx + r * 0.82 * math.cos(rot + math.pi * 2 / 3 * i - math.pi / 2),
                           cy + r * 0.82 * math.sin(rot + math.pi * 2 / 3 * i - math.pi / 2))
                   for i in range(3)]
            tri.moveTo(pts[0]); tri.lineTo(pts[1]); tri.lineTo(pts[2])
            tri.closeSubpath()
            painter.drawPath(tri)
    s.append(("Hexagram", draw_hexagram))

    # 4 — Ankh  (authentic: oval loop + T cross, no overlap)
    def draw_ankh(painter, cx, cy, r, color):
        painter.setPen(QPen(color, r * 0.09, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        # Oval loop
        loop_cy = cy - r * 0.4
        loop_rx, loop_ry = r * 0.28, r * 0.36
        painter.drawEllipse(QPointF(cx, loop_cy), loop_rx, loop_ry)
        # Vertical stem starts BELOW the loop
        stem_top = loop_cy + loop_ry
        painter.drawLine(QPointF(cx, stem_top), QPointF(cx, cy + r * 0.82))
        # Horizontal crossbar
        painter.drawLine(QPointF(cx - r * 0.52, cy + r * 0.06),
                         QPointF(cx + r * 0.52, cy + r * 0.06))
    s.append(("Ankh", draw_ankh))

    # 5 — Triquetra  (three interlaced 240° arcs inside enclosing circle)
    def draw_triquetra(painter, cx, cy, r, color):
        painter.setPen(QPen(color, r * 0.09, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        rr = r * 0.50
        D = rr / math.sqrt(3)
        for i in range(3):
            ang = i * 2 * math.pi / 3 - math.pi / 2
            ox = cx + D * math.cos(ang)
            oy = cy + D * math.sin(ang)
            back_deg = math.degrees(math.atan2(-(cy - oy), cx - ox)) % 360
            start_deg = (back_deg + 60) % 360
            painter.drawArc(QRectF(ox - rr, oy - rr, rr * 2, rr * 2),
                            int(round(start_deg * 16)), 240 * 16)
        # Traditional enclosing circle
        painter.setPen(QPen(color, r * 0.055))
        painter.drawEllipse(QPointF(cx, cy), r * 0.82, r * 0.82)
    s.append(("Triquetra", draw_triquetra))

    # 6 — Yin-Yang  (stylized outline — no black/white fill, works on any sphere color)
    def draw_yinyang(painter, cx, cy, r, color):
        rr = r * 0.78
        painter.setBrush(Qt.NoBrush)
        # Outer circle
        painter.setPen(QPen(color, r * 0.07))
        painter.drawEllipse(QPointF(cx, cy), rr, rr)
        # S-dividing curve: upper small right-half arc + lower small left-half arc
        painter.setPen(QPen(color, r * 0.07, Qt.SolidLine, Qt.RoundCap))
        s_path = QPainterPath()
        s_path.moveTo(cx, cy - rr)
        # Upper small circle right half (CW: 90° → -180° → 270° = center)
        s_path.arcTo(cx - rr / 2, cy - rr, rr, rr, 90, -180)
        # Lower small circle left half (CCW: 90° → +180° → 270° = bottom)
        s_path.arcTo(cx - rr / 2, cy, rr, rr, 90, 180)
        painter.drawPath(s_path)
        # Upper dot (filled)
        sz = rr * 0.12
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy - rr / 2), sz, sz)
        # Lower dot (outline only)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(color, r * 0.06))
        painter.drawEllipse(QPointF(cx, cy + rr / 2), sz, sz)
    s.append(("Yin-Yang", draw_yinyang))

    # 7 — Om / Aum  (Unicode ॐ rendered with Devanagari system font)
    def draw_om(painter, cx, cy, r, color):
        painter.setPen(QPen(color, 1))
        painter.setBrush(QBrush(color))
        # Nirmala UI ships with Windows 8.1+ and supports Devanagari perfectly
        font = QFont("Nirmala UI")
        font.setPixelSize(int(r * 1.55))
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(QRectF(cx - r, cy - r * 1.05, r * 2, r * 2.1),
                         Qt.AlignCenter, "\u0950")   # ॐ
    s.append(("Om", draw_om))

    # 8 — Infinity  (lemniscate approximated with cubic beziers)
    def draw_infinity(painter, cx, cy, r, color):
        painter.setPen(QPen(color, r * 0.1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        w = r * 0.76   # half-width of each lobe
        h = r * 0.40   # half-height
        c = w * 0.55   # control-point offset
        p = QPainterPath()
        p.moveTo(cx, cy)
        p.cubicTo(cx + c, cy - h, cx + w, cy - h, cx + w, cy)
        p.cubicTo(cx + w, cy + h, cx + c, cy + h, cx,     cy)
        p.cubicTo(cx - c, cy + h, cx - w, cy + h, cx - w, cy)
        p.cubicTo(cx - w, cy - h, cx - c, cy - h, cx,     cy)
        painter.drawPath(p)
    s.append(("Infinity", draw_infinity))

    # 9 — Flower of Life  (7 equal circles, authentic pattern)
    def draw_flower(painter, cx, cy, r, color):
        painter.setPen(QPen(color, r * 0.055))
        painter.setBrush(Qt.NoBrush)
        rr = r * 0.36
        painter.drawEllipse(QPointF(cx, cy), rr, rr)
        for i in range(6):
            a = i * math.pi / 3
            painter.drawEllipse(QPointF(cx + rr * math.cos(a), cy + rr * math.sin(a)), rr, rr)
        # Outer ring to complete the pattern
        painter.drawEllipse(QPointF(cx, cy), rr * 2, rr * 2)
    s.append(("Flower of Life", draw_flower))

    # 10 — Crescent Moon  (path subtraction — correct)
    def draw_crescent(painter, cx, cy, r, color):
        p = QPainterPath()
        p.addEllipse(QPointF(cx, cy), r * 0.75, r * 0.75)
        inner = QPainterPath()
        inner.addEllipse(QPointF(cx + r * 0.3, cy), r * 0.62, r * 0.62)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawPath(p.subtracted(inner))
    s.append(("Crescent Moon", draw_crescent))

    # 11 — Sun  (circle + 8 rays)
    def draw_sun(painter, cx, cy, r, color):
        painter.setPen(QPen(color, r * 0.08, Qt.SolidLine, Qt.RoundCap))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), r * 0.36, r * 0.36)
        for i in range(8):
            a = i * math.pi / 4
            painter.drawLine(QPointF(cx + r * 0.46 * math.cos(a), cy + r * 0.46 * math.sin(a)),
                             QPointF(cx + r * 0.84 * math.cos(a), cy + r * 0.84 * math.sin(a)))
    s.append(("Sun", draw_sun))

    # 12 — Rune: Algiz  (protection — ᛉ)
    def draw_algiz(painter, cx, cy, r, color):
        painter.setPen(QPen(color, r * 0.1, Qt.SolidLine, Qt.RoundCap))
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(QPointF(cx, cy - r * 0.88), QPointF(cx, cy + r * 0.88))
        painter.drawLine(QPointF(cx, cy - r * 0.18), QPointF(cx - r * 0.5, cy - r * 0.72))
        painter.drawLine(QPointF(cx, cy - r * 0.18), QPointF(cx + r * 0.5, cy - r * 0.72))
    s.append(("Algiz Rune", draw_algiz))

    # 13 — Rune: Othala  (heritage — ᛟ, correct shape: diamond + two splayed legs)
    def draw_othala(painter, cx, cy, r, color):
        painter.setPen(QPen(color, r * 0.10, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        # ᛟ = diamond (top/left/right vertices) with two legs from left+right going down-out
        top   = QPointF(cx,             cy - r * 0.82)
        left  = QPointF(cx - r * 0.52,  cy)
        right = QPointF(cx + r * 0.52,  cy)
        lb    = QPointF(cx - r * 0.30,  cy + r * 0.82)   # left foot
        rb    = QPointF(cx + r * 0.30,  cy + r * 0.82)   # right foot
        p = QPainterPath()
        # Diamond sides
        p.moveTo(top);  p.lineTo(left)
        p.moveTo(top);  p.lineTo(right)
        # Legs from left/right down to feet
        p.moveTo(left);  p.lineTo(lb)
        p.moveTo(right); p.lineTo(rb)
        # Crossbar at waist (left to right)
        p.moveTo(left);  p.lineTo(right)
        painter.drawPath(p)
    s.append(("Othala Rune", draw_othala))

    # 14 — Vesica Piscis  (two circles, centers at radius distance apart)
    def draw_vesica(painter, cx, cy, r, color):
        painter.setPen(QPen(color, r * 0.07))
        painter.setBrush(Qt.NoBrush)
        rr = r * 0.62
        off = rr / 2      # correct: distance between centers = radius → off = rr/2? No.
        # Vesica Piscis: two circles of radius rr, centers rr apart
        off = rr * 0.5    # center offset = rr/2 so that center-to-center = rr... wait: off*2 = rr ✓
        painter.drawEllipse(QPointF(cx - off, cy), rr, rr)
        painter.drawEllipse(QPointF(cx + off, cy), rr, rr)
    s.append(("Vesica Piscis", draw_vesica))

    # 15 — Metatron's Cube
    def draw_metatron(painter, cx, cy, r, color):
        painter.setPen(QPen(color, r * 0.038))
        painter.setBrush(Qt.NoBrush)
        rr = r * 0.38
        centers = [(cx, cy)]
        for i in range(6):
            a = i * math.pi / 3
            centers.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        for c in centers:
            painter.drawEllipse(QPointF(c[0], c[1]), rr, rr)
        for i in range(len(centers)):
            for j in range(i + 1, len(centers)):
                painter.drawLine(QPointF(centers[i][0], centers[i][1]),
                                 QPointF(centers[j][0], centers[j][1]))
    s.append(("Metatron's Cube", draw_metatron))

    # 16 — Triskelion  (three spiral arms from center)
    def draw_triskelion(painter, cx, cy, r, color):
        painter.setPen(QPen(color, r * 0.085, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        for i in range(3):
            base_angle = i * math.pi * 2 / 3 - math.pi / 2
            p = QPainterPath()
            steps = 40
            for k in range(steps + 1):
                t = k / steps
                angle = base_angle + t * math.pi * 1.1
                rad = r * 0.08 + r * 0.74 * t
                pt = QPointF(cx + rad * math.cos(angle), cy + rad * math.sin(angle))
                if k == 0:
                    p.moveTo(pt)
                else:
                    p.lineTo(pt)
            painter.drawPath(p)
        painter.drawEllipse(QPointF(cx, cy), r * 0.1, r * 0.1)
    s.append(("Triskelion", draw_triskelion))

    # 17 — Lotus  (8 petals using painter save/translate/rotate — correct transform)
    def draw_lotus(painter, cx, cy, r, color):
        painter.setPen(QPen(color, r * 0.065, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        petals = 8
        for i in range(petals):
            angle_deg = i * 360 / petals - 90
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(angle_deg)
            # Petal: tall ellipse pointing upward (negative y = up in screen)
            p = QPainterPath()
            p.addEllipse(QPointF(0, -r * 0.54), r * 0.18, r * 0.36)
            painter.drawPath(p)
            painter.restore()
        painter.drawEllipse(QPointF(cx, cy), r * 0.17, r * 0.17)
    s.append(("Lotus", draw_lotus))

    # 18 — Tree of Life  (Kabbalah — 10 Sefirot + authentic 22 paths)
    def draw_tree(painter, cx, cy, r, color):
        painter.setPen(QPen(color, r * 0.055))
        painter.setBrush(Qt.NoBrush)
        # Sefirot positions: 0=Keter 1=Binah 2=Chokmah 3=Gevurah 4=Tiferet
        #                    5=Chesed 6=Hod 7=Netzach 8=Yesod 9=Malkuth
        nodes_rel = [
            (0, -0.88),                            # 0 Keter
            (-0.42, -0.50), (0.42, -0.50),         # 1 Binah, 2 Chokmah
            (-0.50, -0.04), (0, -0.04), (0.50, -0.04),  # 3 Gevurah, 4 Tiferet, 5 Chesed
            (-0.42,  0.40), (0.42,  0.40),         # 6 Hod, 7 Netzach
            (0,      0.40),                         # 8 Yesod
            (0,      0.88),                         # 9 Malkuth
        ]
        node_pos = [(cx + x * r, cy + y * r) for x, y in nodes_rel]
        # 22 authentic paths
        edges = [
            (0,1),(0,2),(0,4),
            (1,2),(1,3),(1,4),(2,4),(2,5),
            (3,4),(4,5),(3,6),(4,6),(4,7),(4,8),(5,7),
            (3,8),(5,8),(6,8),(7,8),
            (6,9),(7,9),(8,9),
        ]
        for a, b in edges:
            painter.drawLine(QPointF(node_pos[a][0], node_pos[a][1]),
                             QPointF(node_pos[b][0], node_pos[b][1]))
        painter.setBrush(QBrush(color))
        for nx, ny in node_pos:
            painter.drawEllipse(QPointF(nx, ny), r * 0.075, r * 0.075)
    s.append(("Tree of Life", draw_tree))

    # 19 — Ouroboros  (serpent biting its own tail — arc body + diamond head + forked tongue)
    def draw_ouroboros(painter, cx, cy, r, color):
        rr = r * 0.66
        # Thick body arc (leaving ~50° gap at 3 o'clock position for head/tail junction)
        painter.setPen(QPen(color, r * 0.115, Qt.SolidLine, Qt.RoundCap))
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(QRectF(cx - rr, cy - rr, rr * 2, rr * 2),
                        int(25 * 16), int(310 * 16))
        # Head: diamond shape pointing RIGHT at (cx+rr, cy)
        hx, hy = cx + rr, cy
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        head = QPainterPath()
        head.moveTo(hx + r * 0.18, hy)              # nose
        head.lineTo(hx - r * 0.04, hy - r * 0.17)  # upper jaw
        head.lineTo(hx - r * 0.14, hy)              # throat
        head.lineTo(hx - r * 0.04, hy + r * 0.17)  # lower jaw
        head.closeSubpath()
        painter.drawPath(head)
        # Eye (small hollow ellipse)
        painter.setBrush(QBrush(BG_COLOR))
        painter.drawEllipse(QPointF(hx + r * 0.03, hy - r * 0.065), r * 0.048, r * 0.038)
        # Pupil slit
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(hx + r * 0.03, hy - r * 0.065), r * 0.012, r * 0.030)
        # Forked tongue
        painter.setPen(QPen(color, r * 0.038, Qt.SolidLine, Qt.RoundCap))
        tbase = QPointF(hx + r * 0.16, hy)
        tfork = QPointF(hx + r * 0.25, hy)
        painter.drawLine(tbase, tfork)
        painter.drawLine(tfork, QPointF(hx + r * 0.32, hy - r * 0.08))
        painter.drawLine(tfork, QPointF(hx + r * 0.32, hy + r * 0.08))
    s.append(("Ouroboros", draw_ouroboros))

    # 20 — Caduceus  (staff + wings + two cubic-bezier interweaving snakes)
    def draw_caduceus(painter, cx, cy, r, color):
        painter.setPen(QPen(color, r * 0.08, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        # Staff
        painter.drawLine(QPointF(cx, cy - r * 0.88), QPointF(cx, cy + r * 0.88))
        # Wings: two elegant symmetric curves sweeping outward then back
        for sign in (-1, 1):
            p = QPainterPath()
            p.moveTo(cx, cy - r * 0.58)
            p.cubicTo(cx + sign * r * 0.22, cy - r * 0.92,
                      cx + sign * r * 0.82, cy - r * 0.74,
                      cx + sign * r * 0.68, cy - r * 0.44)
            painter.drawPath(p)
        # Two snakes: smooth cubic bezier with 2 crossings each
        y_top = cy - r * 0.44
        y_bot = cy + r * 0.80
        seg   = (y_bot - y_top) / 2.0
        amp   = r * 0.32
        for sign in (-1, 1):
            p = QPainterPath()
            p.moveTo(cx + sign * amp * 0.5, y_top)
            # First crossing (to opposite side)
            p.cubicTo(cx + sign * amp,        y_top + seg * 0.28,
                      cx - sign * amp,        y_top + seg * 0.72,
                      cx - sign * amp * 0.5,  y_top + seg)
            # Second crossing (back to original side)
            p.cubicTo(cx - sign * amp,        y_top + seg * 1.28,
                      cx + sign * amp,        y_top + seg * 1.72,
                      cx + sign * amp * 0.5,  y_bot)
            painter.drawPath(p)
        # Globe/ball at top of staff
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy - r * 0.88), r * 0.09, r * 0.09)
    s.append(("Caduceus", draw_caduceus))

    # 21 — Hamsa  (Hand of Fatima — curved palm + 5 rounded fingers + evil eye)
    def draw_hamsa(painter, cx, cy, r, color):
        painter.setPen(QPen(color, r * 0.075, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        pw   = r * 0.44    # palm half-width at finger base
        pw_b = r * 0.28    # palm half-width at wrist
        pt   = cy - r * 0.04   # palm top (finger base)
        pb   = cy + r * 0.68   # palm bottom (wrist)
        # Palm: organic curved shape wider at top, narrower at wrist
        palm = QPainterPath()
        palm.moveTo(cx - pw, pt)
        palm.lineTo(cx + pw, pt)
        palm.cubicTo(cx + pw + r*0.06, (pt+pb)*0.55,
                     cx + pw_b + r*0.04, pb - r*0.10,
                     cx + pw_b, pb)
        palm.quadTo(cx, pb + r * 0.06, cx - pw_b, pb)
        palm.cubicTo(cx - pw_b - r*0.04, pb - r*0.10,
                     cx - pw - r*0.06, (pt+pb)*0.55,
                     cx - pw, pt)
        palm.closeSubpath()
        painter.drawPath(palm)
        # Five fingers (symmetric pair arrangement, middle is tallest)
        f_xs = [-pw * 0.86, -pw * 0.40, 0.0, pw * 0.40, pw * 0.86]
        f_hs = [r * 0.40,   r * 0.60,   r * 0.74, r * 0.60, r * 0.40]
        fw   = r * 0.052
        for fx, fh in zip(f_xs, f_hs):
            x = cx + fx
            painter.drawLine(QPointF(x, pt), QPointF(x, pt - fh))
            # Rounded fingertip arc (upper semicircle)
            painter.drawArc(QRectF(x - fw, pt - fh - fw * 1.8, fw * 2, fw * 2),
                            0, 180 * 16)
        # Eye (nazar) in center of palm
        ey, ew, eh = cy + r * 0.30, r * 0.20, r * 0.12
        pe = QPainterPath()
        pe.moveTo(cx - ew, ey)
        pe.quadTo(cx, ey - eh, cx + ew, ey)
        pe.quadTo(cx, ey + eh, cx - ew, ey)
        painter.drawPath(pe)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, ey), eh * 0.44, eh * 0.44)
    s.append(("Hamsa", draw_hamsa))

    # 22 — Rune: Sowilo  (sun/lightning — ᛋ)
    def draw_sowilo(painter, cx, cy, r, color):
        painter.setPen(QPen(color, r * 0.12, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        p = QPainterPath()
        p.moveTo(cx - r * 0.28, cy - r * 0.88)
        p.lineTo(cx + r * 0.38, cy - r * 0.88)
        p.lineTo(cx - r * 0.38, cy + r * 0.88)
        p.lineTo(cx + r * 0.28, cy + r * 0.88)
        painter.drawPath(p)
    s.append(("Sowilo Rune", draw_sowilo))

    # 23 — Mandala  (two rings + 4 petal circles + 8 spokes)
    def draw_mandala(painter, cx, cy, r, color):
        painter.setPen(QPen(color, r * 0.058))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), r * 0.82, r * 0.82)
        painter.drawEllipse(QPointF(cx, cy), r * 0.44, r * 0.44)
        for i in range(4):
            a = i * math.pi / 2 + math.pi / 4
            ox = cx + r * 0.44 * math.cos(a)
            oy = cy + r * 0.44 * math.sin(a)
            painter.drawEllipse(QPointF(ox, oy), r * 0.28, r * 0.28)
        for i in range(8):
            a = i * math.pi / 4
            painter.drawLine(QPointF(cx + r * 0.44 * math.cos(a), cy + r * 0.44 * math.sin(a)),
                             QPointF(cx + r * 0.82 * math.cos(a), cy + r * 0.82 * math.sin(a)))
    s.append(("Mandala", draw_mandala))

    # 24 — Compass  (four cardinal arrows with proper arrowhead math)
    def draw_compass(painter, cx, cy, r, color):
        painter.setBrush(QBrush(color))
        # North (primary, longer), E, S, W
        directions = [
            (0, -r * 0.82, r * 0.13),
            (r * 0.58, 0,  r * 0.10),
            (0,  r * 0.58, r * 0.10),
            (-r * 0.58, 0, r * 0.10),
        ]
        for tx, ty, hw in directions:
            length = math.hypot(tx, ty)
            ux, uy = tx / length, ty / length
            px, py = -uy, ux
            painter.setPen(QPen(color, r * 0.07, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(cx, cy), QPointF(cx + tx, cy + ty))
            # Arrowhead
            tip  = QPointF(cx + tx, cy + ty)
            base_x = cx + tx - ux * r * 0.22
            base_y = cy + ty - uy * r * 0.22
            arr = QPainterPath()
            arr.moveTo(tip)
            arr.lineTo(base_x + px * hw, base_y + py * hw)
            arr.lineTo(base_x - px * hw, base_y - py * hw)
            arr.closeSubpath()
            painter.setPen(Qt.NoPen)
            painter.drawPath(arr)
        painter.drawEllipse(QPointF(cx, cy), r * 0.09, r * 0.09)
    s.append(("Compass", draw_compass))

    # 25 — Dharma Wheel  (8 spokes between inner and outer ring)
    def draw_dharma(painter, cx, cy, r, color):
        painter.setPen(QPen(color, r * 0.065))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), r * 0.82, r * 0.82)
        painter.drawEllipse(QPointF(cx, cy), r * 0.22, r * 0.22)
        for i in range(8):
            a = i * math.pi / 4
            painter.drawLine(QPointF(cx + r * 0.22 * math.cos(a), cy + r * 0.22 * math.sin(a)),
                             QPointF(cx + r * 0.82 * math.cos(a), cy + r * 0.82 * math.sin(a)))
    s.append(("Dharma Wheel", draw_dharma))

    # 26 — Merkaba  (Star Tetrahedron: two interlaced triangles + inner circle)
    def draw_merkaba(painter, cx, cy, r, color):
        painter.setPen(QPen(color, r * 0.075, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        for rot in (0.0, math.pi):
            tri = QPainterPath()
            pts = [QPointF(cx + r * 0.82 * math.cos(rot + math.pi * 2 / 3 * i - math.pi / 2),
                           cy + r * 0.82 * math.sin(rot + math.pi * 2 / 3 * i - math.pi / 2))
                   for i in range(3)]
            tri.moveTo(pts[0]); tri.lineTo(pts[1]); tri.lineTo(pts[2])
            tri.closeSubpath()
            painter.drawPath(tri)
        painter.drawEllipse(QPointF(cx, cy), r * 0.22, r * 0.22)
    s.append(("Merkaba", draw_merkaba))

    return s

SYMBOLS = _build_symbols()


# ─────────────────────────────────────────────
#  SYMBOL PICKER DIALOG
# ─────────────────────────────────────────────
class SymbolButton(QWidget):
    clicked = pyqtSignal(int)

    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self.index = index
        self.selected = False
        self.setFixedSize(68, 68)
        self.setCursor(Qt.PointingHandCursor)
        self.color = QColor(SYMBOL_COLORS[index % len(SYMBOL_COLORS)])

    def setSelected(self, val: bool):
        self.selected = val
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        r = min(cx, cy) - 4

        if self.selected:
            painter.setPen(QPen(GOLD, 2.5))
            painter.setBrush(QBrush(QColor(60, 30, 100, 200)))
        else:
            painter.setPen(QPen(self.color.darker(150), 1.5))
            painter.setBrush(QBrush(QColor(20, 5, 45, 200)))
        painter.drawEllipse(QPointF(cx, cy), r, r)

        _, draw_fn = SYMBOLS[self.index]
        draw_fn(painter, cx, cy, r * 0.72, self.color)

        painter.end()

    def mousePressEvent(self, event):
        self.clicked.emit(self.index)


class SymbolPicker(QDialog):
    def __init__(self, current: int = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scegli Simbolo")
        self.setStyleSheet("""
            QDialog { background: #07001a; }
            QLabel { color: #a060ff; font-size: 13px; }
            QPushButton {
                background: #1a0050; color: #d4c8ff; border: 1px solid #5020b0;
                padding: 6px 18px; border-radius: 6px;
            }
            QPushButton:hover { background: #2a0070; }
        """)
        self.selected = current
        self.buttons: List[SymbolButton] = []

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("   Scegli un simbolo per la nota:"))

        scroll = QScrollArea()
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.setWidgetResizable(True)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        grid = QGridLayout(container)
        grid.setSpacing(6)

        cols = 7
        for i, (name, _) in enumerate(SYMBOLS):
            btn = SymbolButton(i)
            btn.setToolTip(name)
            btn.clicked.connect(self._select)
            if i == current:
                btn.setSelected(True)
            self.buttons.append(btn)
            grid.addWidget(btn, i // cols, i % cols)

        scroll.setWidget(container)
        layout.addWidget(scroll)

        name_label = QLabel(SYMBOLS[current][0])
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("color: #ffe08a; font-size: 12px;")
        self.name_label = name_label
        layout.addWidget(name_label)

        ok_btn = QPushButton("Conferma")
        ok_btn.clicked.connect(self.accept)
        layout.addWidget(ok_btn)
        self.setMinimumSize(520, 420)

    def _select(self, index: int):
        self.buttons[self.selected].setSelected(False)
        self.selected = index
        self.buttons[index].setSelected(True)
        self.name_label.setText(SYMBOLS[index][0])


# ─────────────────────────────────────────────
#  NOTE EDITOR DIALOG
# ─────────────────────────────────────────────
class NoteEditor(QDialog):
    def __init__(self, title="", content="", symbol=0, color="#a060ff", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Modifica Nota")
        self.setMinimumSize(520, 420)
        self.result_title = title
        self.result_content = content
        self.result_symbol = symbol
        self.result_color = color

        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #0d0030, stop:1 #050018);
            }
            QLabel {
                color: #9060e0; font-size: 11px; font-weight: bold; padding: 2px 0;
            }
            QLabel#dlg_header {
                color: #d6c4ff; font-size: 15px; font-weight: bold;
                letter-spacing: 4px; padding: 2px 0 8px 0;
            }
            QLineEdit {
                background: #090022;
                color: #e8d8ff;
                border: 1px solid #4a1890;
                border-bottom: 2px solid #7030d0;
                padding: 8px 10px;
                border-radius: 6px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #7030d0;
                border-bottom: 2px solid #a050ff;
                background: #0d0030;
            }
            QTextEdit {
                background: #060016;
                color: #daccff;
                border: 1px solid #381070;
                border-left: 2px solid #6020c0;
                padding: 10px;
                border-radius: 6px;
                font-size: 13px;
            }
            QTextEdit:focus {
                border: 1px solid #6020c0;
                border-left: 2px solid #9040e0;
            }
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #220060, stop:1 #120038);
                color: #c8b8f0; border: 1px solid #5020a0;
                padding: 7px 20px; border-radius: 7px; font-size: 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #340090, stop:1 #1c0050);
                color: #ffffff; border-color: #8040e0;
            }
            QPushButton#ok_btn {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #4800c0, stop:1 #280070);
                border-color: #9050e0; color: #ffffff;
            }
            QPushButton#ok_btn:hover {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #6000f0, stop:1 #380090);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(7)

        # Header
        header = QLabel("◈  MODIFICA  NOTA  ◈")
        header.setObjectName("dlg_header")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Title
        layout.addWidget(QLabel("Titolo"))
        self.title_edit = QLineEdit(title)
        self.title_edit.setPlaceholderText("Titolo della nota…")
        layout.addWidget(self.title_edit)

        # Content
        layout.addWidget(QLabel("Contenuto"))
        self.content_edit = QTextEdit()
        self.content_edit.setPlainText(content)
        self.content_edit.setPlaceholderText("Scrivi qui le tue idee, pensieri, filosofia…")
        layout.addWidget(self.content_edit)

        # Symbol + Color row
        row = QHBoxLayout()
        row.setSpacing(10)
        self.sym_preview = SymbolButton(symbol)
        self.sym_preview.setFixedSize(60, 60)
        self.sym_preview.clicked.connect(self._pick_symbol)
        row.addWidget(self.sym_preview)

        sym_lbl = QLabel(f"{SYMBOLS[symbol][0]}")
        sym_lbl.setStyleSheet("color:#ffe08a; font-size:13px; font-weight:bold;")
        self.sym_lbl = sym_lbl
        row.addWidget(sym_lbl)

        row.addStretch()

        color_btn = QPushButton("Colore sfera")
        color_btn.clicked.connect(self._pick_color)
        self.color_btn = color_btn
        self._update_color_btn()
        row.addWidget(color_btn)

        layout.addLayout(row)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Annulla")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)

        ok = QPushButton("Salva")
        ok.setObjectName("ok_btn")
        ok.clicked.connect(self._save)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

    def _pick_symbol(self, _=None):
        dlg = SymbolPicker(self.result_symbol, self)
        if dlg.exec_():
            self.result_symbol = dlg.selected
            self.sym_preview.index = dlg.selected
            self.sym_preview.color = QColor(SYMBOL_COLORS[dlg.selected % len(SYMBOL_COLORS)])
            self.sym_preview.update()
            self.sym_lbl.setText(f"  {SYMBOLS[dlg.selected][0]}")

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self.result_color), self, "Scegli colore sfera")
        if c.isValid():
            self.result_color = c.name()
            self._update_color_btn()

    def _update_color_btn(self):
        self.color_btn.setStyleSheet(
            f"background:{self.result_color}; color:#fff; border:1px solid #5020b0; padding:5px 12px; border-radius:6px;"
        )

    def _save(self):
        self.result_title = self.title_edit.text().strip() or "Senza titolo"
        self.result_content = self.content_edit.toPlainText()
        self.accept()


# ─────────────────────────────────────────────
#  NODE ITEM  (draggable sphere in the grid)
# ─────────────────────────────────────────────
class NodeItem(QGraphicsEllipseItem):
    RADIUS = 46

    def __init__(self, nid: int, title: str, content: str, symbol: int,
                 color: str, x: float, y: float, scene_ref):
        r = self.RADIUS
        super().__init__(-r, -r, r * 2, r * 2)
        self.nid = nid
        self.title = title
        self.content = content
        self.symbol = symbol
        self.node_color = QColor(color)
        self.scene_ref = scene_ref
        self.setPos(x, y)
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(2)
        self.setPen(QPen(Qt.NoPen))
        self.setBrush(QBrush(Qt.NoBrush))
        self._drag_start = None
        self._update_tooltip()

    def _update_tooltip(self):
        preview = self.content[:120].replace("\n", " ")
        if len(self.content) > 120:
            preview += "…"
        tip = f"<b style='color:#ffe08a'>{self.title}</b>"
        if preview:
            tip += f"<br><span style='color:#c0b0e0'>{preview}</span>"
        self.setToolTip(tip)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.scene_ref.node_moved(self)
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.scene_ref.persist_node_pos(self)

    def boundingRect(self) -> QRectF:
        r = self.RADIUS
        pad = 42
        return QRectF(-r - pad, -r - pad, (r + pad) * 2, (r + pad) * 2 + 26)

    def shape(self) -> QPainterPath:
        p = QPainterPath()
        r = self.RADIUS
        p.addEllipse(QPointF(0, 0), r, r)
        return p

    def paint(self, painter, option, widget=None):
        r = self.RADIUS
        cx, cy = 0.0, 0.0
        sel = self.isSelected()
        base = QColor(self.node_color)
        painter.setRenderHint(QPainter.Antialiasing)

        # ── Outer halo glow — 4 soft layers ───────────────────
        for gr, ga in [(r+34, 9), (r+22, 20), (r+12, 42), (r+5, 78)]:
            gc = QColor(base)
            gc.setAlpha(ga)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(gc))
            painter.drawEllipse(QPointF(cx, cy), gr, gr)

        # ── Hex socket frame (FFX Sphere-Grid node) ───────────
        hexR = r + 10
        verts = []
        hexpath = QPainterPath()
        for i in range(6):
            a = math.pi / 3 * i - math.pi / 2
            vx = cx + hexR * math.cos(a)
            vy = cy + hexR * math.sin(a)
            verts.append((vx, vy))
            if i == 0:
                hexpath.moveTo(vx, vy)
            else:
                hexpath.lineTo(vx, vy)
        hexpath.closeSubpath()
        frame_c = QColor(GOLD) if sel else base.lighter(235)
        frame_c.setAlpha(225 if sel else 120)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(frame_c, 1.6))
        painter.drawPath(hexpath)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(frame_c))
        for vx, vy in verts:
            painter.drawEllipse(QPointF(vx, vy), 2.3, 2.3)

        # ── Sphere body — deep radial gradient ─────────────────
        grad = QRadialGradient(cx - r*0.30, cy - r*0.32, r*1.55)
        grad.setColorAt(0.00, base.lighter(248))
        grad.setColorAt(0.16, base.lighter(168))
        grad.setColorAt(0.46, base)
        grad.setColorAt(0.78, base.darker(225))
        grad.setColorAt(1.00, base.darker(440))
        painter.setBrush(QBrush(grad))
        if sel:
            painter.setPen(QPen(GOLD, 2.6))
        else:
            bc = QColor(base)
            bc.setAlpha(255)
            painter.setPen(QPen(bc.lighter(245), 2.0))
        painter.drawEllipse(QPointF(cx, cy), r, r)

        # ── Clipped interior: specular gloss + bottom shadow ──
        painter.save()
        clip = QPainterPath()
        clip.addEllipse(QPointF(cx, cy), r - 0.8, r - 0.8)
        painter.setClipPath(clip)

        spec = QRadialGradient(cx - r*0.30, cy - r*0.44, r*0.80)
        spec.setColorAt(0.00, QColor(255, 255, 255, 140))
        spec.setColorAt(0.42, QColor(255, 255, 255,  30))
        spec.setColorAt(1.00, QColor(255, 255, 255,   0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(spec))
        painter.drawEllipse(QPointF(cx - r*0.10, cy - r*0.20), r*0.80, r*0.62)

        sh = QRadialGradient(cx + r*0.16, cy + r*0.36, r*0.95)
        sh.setColorAt(0.00, QColor(0, 0, 12, 0))
        sh.setColorAt(0.72, QColor(0, 0, 12, 0))
        sh.setColorAt(1.00, QColor(0, 0, 12, 130))
        painter.setBrush(QBrush(sh))
        painter.drawEllipse(QPointF(cx, cy), r, r)
        painter.restore()

        # ── Inner decorative rings ─────────────────────────────
        for ring_r, ring_a in [(r*0.90, 55), (r*0.70, 26)]:
            ic = QColor(base)
            ic.setAlpha(ring_a)
            painter.setPen(QPen(ic.lighter(280), 0.8))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), ring_r, ring_r)

        # ── Symbol — centred, full size ────────────────────────
        _, draw_fn = SYMBOLS[self.symbol]
        draw_fn(painter, cx, cy, r*0.56, QColor(255, 255, 255, 242))

        # ── Title — floating pill below the sphere ─────────────
        painter.setFont(QFont("Arial", 7, QFont.Bold))
        fm = painter.fontMetrics()
        label = fm.elidedText(self.title, Qt.ElideRight, 134)
        tw = fm.horizontalAdvance(label) + 16
        th = fm.height() + 5
        pill = QRectF(cx - tw/2, cy + r + 9, tw, th)
        painter.setBrush(QBrush(QColor(10, 3, 26, 218)))
        pc = QColor(GOLD) if sel else base.lighter(215)
        pc.setAlpha(215 if sel else 150)
        painter.setPen(QPen(pc, 1.0))
        painter.drawRoundedRect(pill, th/2, th/2)
        painter.setPen(QPen(QColor(249, 242, 255, 252)))
        painter.drawText(pill, Qt.AlignCenter, label)

    def contextMenuEvent(self, event):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background:#0e0030; color:#d4c8ff; border:1px solid #4020a0; }
            QMenu::item:selected { background:#2a0070; }
        """)
        edit_act  = menu.addAction("✏️  Modifica nota")
        conn_act  = menu.addAction("🔗  Connetti / Disconnetti")
        menu.addSeparator()
        del_act   = menu.addAction("🗑️  Elimina sfera")
        chosen = menu.exec_(event.screenPos())
        if chosen == edit_act:
            self.scene_ref.edit_node(self)
        elif chosen == conn_act:
            self.scene_ref.start_connect(self)
        elif chosen == del_act:
            self.scene_ref.delete_node(self)

    def mouseDoubleClickEvent(self, event):
        self.scene_ref.edit_node(self)


# ─────────────────────────────────────────────
#  EDGE ITEM  (glowing tri-layer connection line)
# ─────────────────────────────────────────────
class EdgeItem(QGraphicsItem):
    """FFX-style energy path — gradient core flowing between the two node colours,
    with a glowing pulse node at its midpoint."""

    def __init__(self, p1: QPointF, p2: QPointF, c1=None, c2=None):
        super().__init__()
        self._p1 = QPointF(p1)
        self._p2 = QPointF(p2)
        self._c1 = QColor(c1) if c1 is not None else QColor(140, 95, 255)
        self._c2 = QColor(c2) if c2 is not None else QColor(140, 95, 255)
        self.setZValue(1)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)

    def setLine(self, x1: float, y1: float, x2: float, y2: float):
        self.prepareGeometryChange()
        self._p1 = QPointF(x1, y1)
        self._p2 = QPointF(x2, y2)
        self.update()

    def set_colors(self, c1, c2):
        self._c1 = QColor(c1)
        self._c2 = QColor(c2)
        self.update()

    def boundingRect(self) -> QRectF:
        m = 22.0
        x0 = min(self._p1.x(), self._p2.x()) - m
        y0 = min(self._p1.y(), self._p2.y()) - m
        w  = abs(self._p2.x() - self._p1.x()) + m * 2
        h  = abs(self._p2.y() - self._p1.y()) + m * 2
        return QRectF(x0, y0, w, h)

    def _grad(self, a1: int, a2: int) -> QLinearGradient:
        g = QLinearGradient(self._p1, self._p2)
        c1 = QColor(self._c1); c1.setAlpha(a1)
        c2 = QColor(self._c2); c2.setAlpha(a2)
        cm = QColor((c1.red()   + c2.red())   // 2,
                    (c1.green() + c2.green()) // 2,
                    (c1.blue()  + c2.blue())  // 2,
                    max(a1, a2))
        g.setColorAt(0.0, c1)
        g.setColorAt(0.5, cm.lighter(150))
        g.setColorAt(1.0, c2)
        return g

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        # Layer 1 — wide soft haze (gradient)
        painter.setPen(QPen(QBrush(self._grad(26, 26)), 15,
                            Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(self._p1, self._p2)
        # Layer 2 — mid glow (gradient)
        painter.setPen(QPen(QBrush(self._grad(72, 72)), 5.5,
                            Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(self._p1, self._p2)
        # Layer 3 — bright near-white core spine
        painter.setPen(QPen(QColor(240, 232, 255, 205), 1.6,
                            Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(self._p1, self._p2)
        # Pulse node at midpoint
        mx = (self._p1.x() + self._p2.x()) / 2
        my = (self._p1.y() + self._p2.y()) / 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(235, 225, 255, 60)))
        painter.drawEllipse(QPointF(mx, my), 5.0, 5.0)
        painter.setBrush(QBrush(QColor(255, 255, 255, 235)))
        painter.drawEllipse(QPointF(mx, my), 2.0, 2.0)


# ─────────────────────────────────────────────
#  SPHERE GRID SCENE
# ─────────────────────────────────────────────
class SphereScene(QGraphicsScene):
    notes_changed = pyqtSignal()

    def __init__(self, db: DB, parent=None):
        super().__init__(parent)
        self.db = db
        self.nodes: dict[int, NodeItem] = {}
        self.edge_lines: dict[tuple, EdgeItem] = {}
        self.connect_mode = False
        self.connect_src: Optional[NodeItem] = None
        self.stars: List[Tuple[float, float, float, float]] = []
        self._gen_stars(520)
        self._load()

    def _gen_stars(self, n):
        # Each star: (x, y, size, twinkle_base) — more variety for depth effect
        self.stars = [(random.uniform(-2500, 2500),
                       random.uniform(-2500, 2500),
                       random.uniform(0.4, 2.8),
                       random.uniform(120, 210)) for _ in range(n)]

    def _load(self):
        for row in self.db.get_notes():
            nid, title, content, symbol, color, x, y = row
            self._add_node_item(nid, title, content, symbol, color, x, y)
        for src, dst in self.db.get_connections():
            self._draw_edge(src, dst)

    def _add_node_item(self, nid, title, content, symbol, color, x, y):
        item = NodeItem(nid, title, content, symbol, color, x, y, self)
        self.addItem(item)
        self.nodes[nid] = item
        return item

    def _draw_edge(self, src, dst):
        key = (min(src, dst), max(src, dst))
        if key in self.edge_lines:
            return
        s_id, d_id = key
        if s_id not in self.nodes or d_id not in self.nodes:
            return
        a = self.nodes[s_id]
        b = self.nodes[d_id]
        line = EdgeItem(a.pos(), b.pos(), a.node_color, b.node_color)
        self.addItem(line)
        self.edge_lines[key] = line

    def node_moved(self, item: NodeItem):
        """Live edge geometry update during a drag (no DB writes)."""
        for key, line in self.edge_lines.items():
            src_id, dst_id = key
            if item.nid in (src_id, dst_id):
                if src_id in self.nodes and dst_id in self.nodes:
                    sp = self.nodes[src_id].pos()
                    dp = self.nodes[dst_id].pos()
                    line.setLine(sp.x(), sp.y(), dp.x(), dp.y())

    def persist_node_pos(self, item: NodeItem):
        """Commit a node's final position to the DB (called on drag release)."""
        p = item.pos()
        self.db.update_pos(item.nid, p.x(), p.y())

    def add_node(self, x=0.0, y=0.0):
        nid = self.db.add_note("Nuova Sfera", "", 0, "#a060ff", x, y)
        item = self._add_node_item(nid, "Nuova Sfera", "", 0, "#a060ff", x, y)
        self.edit_node(item)
        self.notes_changed.emit()

    def edit_node(self, item: NodeItem):
        dlg = NoteEditor(item.title, item.content, item.symbol,
                         item.node_color.name())
        if dlg.exec_():
            item.title   = dlg.result_title
            item.content = dlg.result_content
            item.symbol  = dlg.result_symbol
            item.node_color = QColor(dlg.result_color)
            self.db.update_note(item.nid, item.title, item.content,
                                item.symbol, dlg.result_color)
            item._update_tooltip()
            item.update()
            # refresh gradients on connected edges to match the new colour
            for key, line in self.edge_lines.items():
                src_id, dst_id = key
                if item.nid in (src_id, dst_id):
                    if src_id in self.nodes and dst_id in self.nodes:
                        line.set_colors(self.nodes[src_id].node_color,
                                        self.nodes[dst_id].node_color)
            self.notes_changed.emit()

    def delete_node(self, item: NodeItem):
        keys_to_remove = [k for k in self.edge_lines if item.nid in k]
        for k in keys_to_remove:
            self.removeItem(self.edge_lines.pop(k))
        self.db.delete_note(item.nid)
        del self.nodes[item.nid]
        self.removeItem(item)
        self.notes_changed.emit()

    def start_connect(self, item: NodeItem):
        self.connect_mode = True
        self.connect_src = item
        # visual feedback
        item.setSelected(True)

    def finish_connect(self, item: NodeItem):
        if self.connect_src is None or item is self.connect_src:
            if self.connect_src is not None:
                self.connect_src.setSelected(False)
            self.connect_mode = False
            self.connect_src = None
            return
        src = self.connect_src.nid
        dst = item.nid
        key = (min(src, dst), max(src, dst))
        if self.db.has_connection(src, dst):
            # remove
            self.db.remove_connection(src, dst)
            if key in self.edge_lines:
                self.removeItem(self.edge_lines.pop(key))
        else:
            self.db.add_connection(src, dst)
            self._draw_edge(src, dst)
        self.connect_src.setSelected(False)
        self.connect_mode = False
        self.connect_src = None

    def drawBackground(self, painter: QPainter, rect: QRectF):
        painter.fillRect(rect, QBrush(BG_COLOR))
        painter.setPen(Qt.NoPen)

        # ── Central deep-space core glow ──────────────────────
        core = QRadialGradient(0, 0, 1600)
        core.setColorAt(0.00, QColor(46, 16, 104, 70))
        core.setColorAt(0.32, QColor(26, 8, 70, 34))
        core.setColorAt(1.00, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(core))
        painter.drawEllipse(QPointF(0, 0), 1600, 1600)

        # ── Layered nebulae (vivid colour clouds) ─────────────
        for nx, ny, nr, r0, g0, b0, a0 in [
            (-560, -360, 780,  92, 26, 210, 46),
            ( 600, -300, 720,  34, 86, 224, 40),
            ( 360,  440, 660, 210, 36, 156, 40),
            (-440,  430, 580,  44, 168, 196, 34),
        ]:
            neb = QRadialGradient(nx, ny, nr)
            neb.setColorAt(0.00, QColor(r0, g0, b0, a0))
            neb.setColorAt(0.45, QColor(r0 // 2, g0 // 2, b0 // 2, a0 // 3))
            neb.setColorAt(1.00, QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(neb))
            painter.drawEllipse(QPointF(nx, ny), nr, nr)

        # ── Hex grid (FFX Sphere Grid) — glows toward centre ──
        sqrt3 = math.sqrt(3)
        hex_r = 70
        col_w = hex_r * 3.0
        row_h = hex_r * sqrt3
        painter.setBrush(Qt.NoBrush)
        cx0 = int(rect.left()  / col_w) - 1
        cx1 = int(rect.right() / col_w) + 2
        ry0 = int(rect.top()   / row_h) - 1
        ry1 = int(rect.bottom()/ row_h) + 2
        for col in range(cx0, cx1):
            for row in range(ry0, ry1):
                hcx = col * col_w + (row % 2) * hex_r * 1.5
                hcy = row * row_h
                d = math.hypot(hcx, hcy)
                a = max(7, int(58 - d * 0.028))
                painter.setPen(QPen(QColor(124, 74, 234, a), 0.9))
                hp = QPainterPath()
                for i in range(6):
                    ang = math.pi / 3 * i + math.pi / 6
                    px = hcx + hex_r * math.cos(ang)
                    py = hcy + hex_r * math.sin(ang)
                    if i == 0:
                        hp.moveTo(px, py)
                    else:
                        hp.lineTo(px, py)
                hp.closeSubpath()
                painter.drawPath(hp)

        # ── Stars — varied brightness, cross-gleam on bright ones ──
        painter.setPen(Qt.NoPen)
        for sx, sy, sr, alpha_base in self.stars:
            if rect.contains(sx, sy):
                star_c = QColor(STAR_COLOR)
                star_c.setAlpha(int(alpha_base))
                painter.setBrush(QBrush(star_c))
                draw_r = sr * 0.55
                painter.drawEllipse(QPointF(sx, sy), draw_r, draw_r)
                if sr > 2.1:
                    gleam = QColor(STAR_COLOR)
                    gleam.setAlpha(int(alpha_base * 0.38))
                    painter.setPen(QPen(gleam, 0.6))
                    gl = draw_r * 1.8
                    painter.drawLine(QPointF(sx - gl, sy), QPointF(sx + gl, sy))
                    painter.drawLine(QPointF(sx, sy - gl), QPointF(sx, sy + gl))
                    painter.setPen(Qt.NoPen)

    def mousePressEvent(self, event):
        if self.connect_mode and event.button() == Qt.LeftButton:
            item = self.itemAt(event.scenePos(), QTransform())
            if isinstance(item, NodeItem):
                self.finish_connect(item)
                return
            else:
                # cancel connect
                self.connect_mode = False
                if self.connect_src:
                    self.connect_src.setSelected(False)
                self.connect_src = None
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.scenePos(), QTransform())
            if not isinstance(item, NodeItem):
                # Add new node
                pos = event.scenePos()
                self.add_node(pos.x(), pos.y())
                return
        super().mouseDoubleClickEvent(event)


# ─────────────────────────────────────────────
#  SPHERE GRID VIEW
# ─────────────────────────────────────────────
class SphereView(QGraphicsView):
    def __init__(self, scene: SphereScene):
        super().__init__(scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSceneRect(-3000, -3000, 6000, 6000)
        self.setStyleSheet("border: none; background: transparent;")
        self._zoom = 1.0
        self._pan_active = False
        self._pan_start = None
        self._last_scroll = QPointF()

    def wheelEvent(self, event):
        factor = 1.12 if event.angleDelta().y() > 0 else 1 / 1.12
        self._zoom = max(0.15, min(4.0, self._zoom * factor))
        self.setTransform(QTransform().scale(self._zoom, self._zoom))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F:
            self.fitInView(self.scene().itemsBoundingRect().adjusted(-80, -80, 80, 80),
                           Qt.KeepAspectRatio)
        elif event.key() == Qt.Key_0:
            self._zoom = 1.0
            self.setTransform(QTransform().scale(1.0, 1.0))
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._pan_active = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_active and self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y())
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._pan_active = False
            self.setCursor(Qt.ArrowCursor)
        else:
            super().mouseReleaseEvent(event)


# ─────────────────────────────────────────────
#  SIDEBAR (note list + search)
# ─────────────────────────────────────────────
class SidebarPanel(QWidget):
    jump_to = pyqtSignal(int)  # note id

    def __init__(self, db: DB, scene: SphereScene, parent=None):
        super().__init__(parent)
        self.db = db
        self.scene = scene
        self.setFixedWidth(268)
        self.setStyleSheet("""
            QWidget { background: #06001a; }
            QLabel  { color: #a060ff; }
            QLineEdit {
                background: #0d002e; color: #d4c8ff;
                border: 1px solid #4a1890; border-radius: 7px;
                padding: 6px 10px; font-size: 12px;
            }
            QLineEdit:focus { border-color: #8040e0; }
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: #0a001e; width: 6px; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #3a1090; border-radius: 3px; min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 10)
        layout.setSpacing(0)

        # ── Ornate header ──────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(72)
        header.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #160040, stop:1 #07001a);
                border-bottom: 1px solid #3a0080;
            }
        """)
        h_lay = QVBoxLayout(header)
        h_lay.setContentsMargins(12, 8, 12, 8)
        h_lay.setSpacing(2)

        title_lbl = QLabel("⬡  SphereNotes")
        title_lbl.setStyleSheet(
            "color:#ffe08a; font-size:15px; font-weight:bold;"
            "background:transparent; border:none;"
        )
        h_lay.addWidget(title_lbl)

        sub_lbl = QLabel("Griglia Sferica Esoterica")
        sub_lbl.setStyleSheet(
            "color:#6040a0; font-size:10px; background:transparent; border:none;"
        )
        h_lay.addWidget(sub_lbl)
        layout.addWidget(header)

        # ── Search ─────────────────────────────────────────────
        search_wrap = QWidget()
        search_wrap.setStyleSheet("background:transparent;")
        sw_lay = QVBoxLayout(search_wrap)
        sw_lay.setContentsMargins(10, 8, 10, 4)

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  Cerca note…")
        self.search.textChanged.connect(self._filter)
        sw_lay.addWidget(self.search)
        layout.addWidget(search_wrap)

        # ── Decorative separator ───────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("QFrame { background:#2a0060; max-height:1px; border:none; }")
        layout.addWidget(sep)

        # ── Note count label ───────────────────────────────────
        self.count_lbl = QLabel("  0 note")
        self.count_lbl.setStyleSheet(
            "color:#5030a0; font-size:10px; padding:4px 12px;"
        )
        layout.addWidget(self.count_lbl)

        # ── Note list ──────────────────────────────────────────
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.list_widget = QWidget()
        self.list_widget.setStyleSheet("background:transparent;")
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(8, 0, 8, 0)
        self.list_layout.setSpacing(5)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.list_widget)
        layout.addWidget(self.scroll)

        # ── Add button ─────────────────────────────────────────
        add_wrap = QWidget()
        add_wrap.setStyleSheet("background:transparent;")
        aw_lay = QVBoxLayout(add_wrap)
        aw_lay.setContentsMargins(10, 6, 10, 0)

        add_btn = QPushButton("✦  Nuova Sfera")
        add_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #28006a, stop:1 #140042);
                color:#d4c8ff; border:1px solid #6030c0;
                padding:8px; border-radius:7px; font-size:12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #380090, stop:1 #1e0055);
                border-color: #9050e8;
            }
        """)
        add_btn.clicked.connect(self._add_center)
        aw_lay.addWidget(add_btn)
        layout.addWidget(add_wrap)

        self.refresh()

    def refresh(self):
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        query = self.search.text().lower()
        count = 0
        for row in self.db.get_notes():
            nid, title, content, symbol, color, x, y = row
            if query and query not in title.lower() and query not in content.lower():
                continue
            count += 1

            # Card frame
            card = QFrame()
            card.setObjectName("noteCard")
            card.setFixedHeight(58)
            card.setStyleSheet(f"""
                QFrame#noteCard {{
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                        stop:0 #120240, stop:1 #0a0122);
                    border: 1px solid #2a1060;
                    border-left: 4px solid {color};
                    border-radius: 8px;
                }}
                QFrame#noteCard:hover {{
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                        stop:0 #1d0966, stop:1 #11033c);
                    border: 1px solid #5a2cc0;
                    border-left: 4px solid {color};
                }}
            """)
            card.setCursor(Qt.PointingHandCursor)

            row_lay = QHBoxLayout(card)
            row_lay.setContentsMargins(8, 4, 12, 4)
            row_lay.setSpacing(10)

            sym_w = SymbolButton(symbol)
            sym_w.setFixedSize(38, 38)
            sym_w.color = QColor(color)
            sym_w.setEnabled(False)
            row_lay.addWidget(sym_w)

            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            text_col.setContentsMargins(0, 0, 0, 0)

            fm_card = card.fontMetrics()
            title_disp = fm_card.elidedText(title, Qt.ElideRight, 168)
            title_lbl = QLabel(title_disp)
            title_lbl.setStyleSheet(
                "color:#ece2ff; font-size:11px; font-weight:bold;"
                " background:transparent; border:none;"
            )
            title_lbl.setWordWrap(False)
            text_col.addWidget(title_lbl)

            snippet = content.replace("\n", " ").strip()
            if snippet:
                snip_disp = fm_card.elidedText(snippet, Qt.ElideRight, 172)
                snip_lbl = QLabel(snip_disp)
                snip_lbl.setStyleSheet(
                    "color:#7058b0; font-size:9px; background:transparent; border:none;"
                )
                snip_lbl.setWordWrap(False)
                text_col.addWidget(snip_lbl)

            row_lay.addLayout(text_col, 1)

            nid_capture = nid
            card.mousePressEvent = lambda _, i=nid_capture: self.jump_to.emit(i)
            self.list_layout.insertWidget(self.list_layout.count() - 1, card)

        self.count_lbl.setText(
            f"  {count} nota" if count == 1 else f"  {count} note"
        )

    def _filter(self):
        self.refresh()

    def _add_center(self):
        self.scene.add_node(
            random.uniform(-300, 300),
            random.uniform(-300, 300)
        )
        self.refresh()


# ─────────────────────────────────────────────
#  HELP OVERLAY
# ─────────────────────────────────────────────
HELP_TEXT = """
CONTROLLI SFEROGRAFIA:

  Doppio click (sfondo)  →  Crea nuova sfera
  Doppio click (sfera)   →  Apri / modifica nota
  Click destro (sfera)   →  Menu contestuale
                            (modifica, connetti, elimina)
  Trascina sfera         →  Riposiziona
  Scroll mouse           →  Zoom in/out
  Tasto centrale drag    →  Naviga la griglia
  F                      →  Fit griglia nello schermo
  0                      →  Reset zoom

CONNESSIONI:
  Click destro → "Connetti / Disconnetti"
  poi click sulla sfera di destinazione.
  Cliccando di nuovo su una sfera già connessa
  si rimuove la connessione.

SIMBOLI SPIRITUALI:
  Ogni sfera può avere un simbolo
  esoterico come topic/categoria.
  (27 simboli disponibili)
"""


# ─────────────────────────────────────────────
#  MAIN WINDOW
# ─────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SphereNotes  ⬡  Griglia Sferica Esoterica")
        self.resize(1300, 820)
        self.setStyleSheet("""
            QMainWindow { background: #07001a; }
            QToolTip {
                background: #0d0030; color: #d4c8ff;
                border: 1px solid #5020b0; padding: 5px 8px;
                font-size: 11px; border-radius: 5px;
            }
        """)

        self.db = DB()
        self.scene = SphereScene(self.db)

        central = QWidget()
        self.setCentralWidget(central)
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        self.sidebar = SidebarPanel(self.db, self.scene)
        h.addWidget(self.sidebar)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color:#2a0060; max-width:1px;")
        h.addWidget(sep)

        self.view = SphereView(self.scene)
        h.addWidget(self.view, 1)

        self.sidebar.jump_to.connect(self._jump_to_node)
        self.scene.notes_changed.connect(self.sidebar.refresh)

        self._build_toolbar()
        self._setup_shortcuts()

        # Status bar
        self.statusBar().setStyleSheet("QStatusBar { background:#07001a; color:#6040b0; font-size:11px; }")
        self.statusBar().showMessage(
            "Doppio-click sullo sfondo per creare una sfera  •  F per fit  •  Scroll per zoom"
        )

        # Seed demo note if empty
        if not self.db.get_notes():
            self._seed_demo()

    def _build_toolbar(self):
        tb = self.addToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        tb.setStyleSheet("""
            QToolBar {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #0e0030, stop:1 #070020);
                border-bottom: 2px solid #2a0070;
                padding: 5px 8px; spacing: 4px;
            }
            QToolButton {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #220065, stop:1 #120040);
                color: #d4c8ff; border: 1px solid #5030b0;
                padding: 5px 14px; border-radius: 6px; font-size: 12px;
            }
            QToolButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #350090, stop:1 #1c0058);
                border-color: #9060e0; color:#ffffff;
            }
            QToolButton:pressed { background:#1a0055; }
            QToolBar::separator {
                background:#3a0080; width:1px; margin:4px 6px;
            }
        """)

        add_act = QAction("✦  Nuova Sfera", self)
        add_act.triggered.connect(lambda: self.scene.add_node(
            random.uniform(-200, 200), random.uniform(-200, 200)))
        tb.addAction(add_act)

        fit_act = QAction("⬡  Fit Griglia", self)
        fit_act.triggered.connect(self._fit)
        tb.addAction(fit_act)

        tb.addSeparator()

        help_act = QAction("？  Aiuto", self)
        help_act.triggered.connect(self._show_help)
        tb.addAction(help_act)

        tb.addSeparator()

        self.status_lbl = QLabel(
            "  ✦  Doppio-click sul canvas → nuova sfera  ·  F → fit  ·  Scroll → zoom"
        )
        self.status_lbl.setStyleSheet(
            "color:#503080; font-size:11px; padding-left:6px;"
        )
        tb.addWidget(self.status_lbl)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+N"), self, lambda: self.scene.add_node(0, 0))
        QShortcut(QKeySequence("F"), self, self._fit)

    def _fit(self):
        r = self.scene.itemsBoundingRect()
        if r.isEmpty():
            return
        self.view.fitInView(r.adjusted(-80, -80, 80, 80), Qt.KeepAspectRatio)

    def _jump_to_node(self, nid: int):
        if nid in self.scene.nodes:
            node = self.scene.nodes[nid]
            self.view.centerOn(node)
            self.scene.clearSelection()
            node.setSelected(True)

    def _show_help(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Aiuto — SphereNotes")
        dlg.setStyleSheet("QDialog{background:#07001a;} QLabel{color:#d4c8ff;font-size:12px;}")
        dlg.setMinimumSize(420, 400)
        layout = QVBoxLayout(dlg)
        lbl = QLabel(HELP_TEXT)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        ok = QPushButton("Chiudi")
        ok.setStyleSheet("QPushButton{background:#1a0050;color:#d4c8ff;border:1px solid #5020b0;padding:6px 18px;border-radius:6px;}")
        ok.clicked.connect(dlg.accept)
        layout.addWidget(ok, alignment=Qt.AlignRight)
        dlg.exec_()

    def _seed_demo(self):
        demo_notes = [
            ("Coscienza", "Cos'è la coscienza?\nEsiste un osservatore oltre la mente?", 1, "#a060ff", 0, 0),
            ("Sincronicità", "Le coincidenze significative di Jung.\nIl mondo risponde ai nostri pensieri?", 2, "#00d4ff", 200, -120),
            ("Eterno Ritorno", "Nietzsche: vivere ogni momento come se dovessi riviverlo infinitamente.", 8, "#ff60c0", -220, -100),
            ("Akasha", "Il registro akashico — memoria cosmica di ogni evento mai accaduto.", 15, "#60ffa0", 180, 180),
            ("Vuoto", "Il vuoto del Buddhismo Zen. Non-mente. Presenza pura.", 6, "#ffaa30", -180, 200),
            ("Logos", "Il principio ordinatore del cosmo. La parola che crea la realtà.", 19, "#30d0ff", 0, 280),
        ]
        ids = []
        for title, content, symbol, color, x, y in demo_notes:
            nid = self.db.add_note(title, content, symbol, color, float(x), float(y))
            item = self.scene._add_node_item(nid, title, content, symbol, color, float(x), float(y))
            ids.append(nid)

        # Connect some
        connections = [(0,1),(1,2),(2,3),(3,4),(4,5),(0,3),(1,4)]
        for a, b in connections:
            if a < len(ids) and b < len(ids):
                self.db.add_connection(ids[a], ids[b])
                self.scene._draw_edge(ids[a], ids[b])

        self.sidebar.refresh()
        QTimer.singleShot(200, self._fit)


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SphereNotes")
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#07001a"))
    palette.setColor(QPalette.WindowText, QColor("#d4c8ff"))
    palette.setColor(QPalette.Base, QColor("#0e0030"))
    palette.setColor(QPalette.AlternateBase, QColor("#1a0040"))
    palette.setColor(QPalette.Text, QColor("#d4c8ff"))
    palette.setColor(QPalette.Button, QColor("#1a0050"))
    palette.setColor(QPalette.ButtonText, QColor("#d4c8ff"))
    palette.setColor(QPalette.Highlight, QColor("#5020b0"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
