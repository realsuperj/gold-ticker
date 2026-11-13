#!/usr/local/bin/python3.9
# -*- coding: utf-8 -*-
"""GoldTicker 图标生成：1024 PNG + AppIcon.icns"""

import os
import subprocess
import sys

import objc
from AppKit import (
    NSBitmapImageRep, NSBitmapImageFileTypePNG, NSBezierPath, NSColor, NSFont,
    NSFontAttributeName, NSFontWeightSemibold, NSForegroundColorAttributeName,
    NSGradient, NSGraphicsContext, NSImage, NSShadow, NSMakeRect, NSString,
)
from Foundation import NSMakePoint, NSMakeSize

SIZE = 1024.0
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PNG = os.path.join(ROOT, "docs", "icon-1024.png")
ICONSET = os.path.join(ROOT, "build", "GoldTicker.iconset")
OUT_ICNS = os.path.join(ROOT, "build", "AppIcon.icns")

GOLD_LIGHT = (1.0, 0.85, 0.40, 1.0)
GOLD = (0.95, 0.71, 0.24, 1.0)
GOLD_DEEP = (0.84, 0.55, 0.12, 1.0)
RED = (1.0, 0.34, 0.30, 1.0)


def col(rgba, alpha=None):
    r, g, b, a = rgba
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, a if alpha is None else alpha)


def draw_background():
    rect = NSMakeRect(0, 0, SIZE, SIZE)
    path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, 228, 228)
    path.addClip()
    grad = NSGradient.alloc().initWithColors_([
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.20, 0.23, 0.30, 1.0),
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.05, 0.06, 0.08, 1.0),
    ])
    grad.drawInRect_angle_(rect, -90)

    # 顶部微弱暖光：单一垂直渐变，避免拼接硬边
    warm = NSGradient.alloc().initWithColors_([
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.16, 0.18, 0.23, 1.0),
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.08, 0.09, 0.12, 1.0),
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.03, 0.035, 0.05, 1.0),
    ])
    warm.drawInRect_angle_(rect, -90)

    # 内描边
    inner = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(3, 3, SIZE - 6, SIZE - 6), 226, 226)
    inner.setLineWidth_(4.0)
    NSColor.colorWithSRGBRed_green_blue_alpha_(1, 1, 1, 0.10).setStroke()
    inner.stroke()


def draw_ore():
    """原石 + 切开一角露出金质断面，断面延伸出一条金脉"""
    pts = [(300, 470), (392, 716), (600, 766), (762, 636), (788, 432), (636, 326), (408, 356)]
    stone = NSBezierPath.bezierPath()
    stone.moveToPoint_(NSMakePoint(*pts[0]))
    for p in pts[1:]:
        stone.lineToPoint_(NSMakePoint(*p))
    stone.closePath()

    NSGraphicsContext.saveGraphicsState()
    xf = __import__("AppKit").NSAffineTransform.transform()
    xf.translateXBy_yBy_(474, 492)
    xf.scaleBy_(1.30)
    xf.rotateByDegrees_(-7)
    xf.translateXBy_yBy_(-512, -508)
    xf.set()

    # 投影
    NSGraphicsContext.saveGraphicsState()
    shadow = NSShadow.alloc().init()
    shadow.setShadowColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(0, 0, 0, 0.85))
    shadow.setShadowBlurRadius_(95)
    shadow.setShadowOffset_(NSMakePoint(0, -44))
    shadow.set()
    NSColor.colorWithSRGBRed_green_blue_alpha_(0.18, 0.11, 0.03, 1.0).setFill()
    stone.fill()
    NSGraphicsContext.restoreGraphicsState()

    stone.addClip()

    # 原石本体
    rock = NSGradient.alloc().initWithColors_([
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.46, 0.31, 0.10, 1.0),
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.26, 0.18, 0.07, 1.0),
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.13, 0.09, 0.05, 1.0),
    ])
    rock.drawInRect_angle_(NSMakeRect(280, 300, 540, 500), 55)

    # 切面
    face = NSBezierPath.bezierPath()
    face.moveToPoint_(NSMakePoint(600, 766))
    face.lineToPoint_(NSMakePoint(762, 636))
    face.lineToPoint_(NSMakePoint(788, 432))
    face.lineToPoint_(NSMakePoint(656, 452))
    face.lineToPoint_(NSMakePoint(560, 600))
    face.closePath()
    gold = NSGradient.alloc().initWithColors_([
        NSColor.colorWithSRGBRed_green_blue_alpha_(1.00, 0.88, 0.50, 1.0),
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.97, 0.72, 0.21, 1.0),
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.80, 0.48, 0.07, 1.0),
    ])
    NSGraphicsContext.saveGraphicsState()
    face.addClip()
    gold.drawInRect_angle_(NSMakeRect(540, 400, 280, 400), -95)
    NSGraphicsContext.restoreGraphicsState()

    # 断面边缘的高光棱线
    edge = NSBezierPath.bezierPath()
    edge.moveToPoint_(NSMakePoint(600, 766))
    edge.lineToPoint_(NSMakePoint(560, 600))
    edge.lineToPoint_(NSMakePoint(656, 452))
    edge.setLineWidth_(11)
    edge.setLineCapStyle_(1)
    edge.setLineJoinStyle_(1)
    NSColor.colorWithSRGBRed_green_blue_alpha_(1.0, 0.96, 0.76, 0.92).setStroke()
    edge.stroke()

    # 从断面延伸出的矿脉
    vein = NSBezierPath.bezierPath()
    vein.moveToPoint_(NSMakePoint(556, 604))
    vein.lineToPoint_(NSMakePoint(470, 560))
    vein.lineToPoint_(NSMakePoint(404, 470))
    vein.lineToPoint_(NSMakePoint(300, 424))
    vein.setLineWidth_(38)
    vein.setLineCapStyle_(1)
    vein.setLineJoinStyle_(1)
    NSColor.colorWithSRGBRed_green_blue_alpha_(1.0, 0.78, 0.26, 0.38).setStroke()
    vein.stroke()

    core = NSBezierPath.bezierPath()
    core.moveToPoint_(NSMakePoint(556, 604))
    core.lineToPoint_(NSMakePoint(470, 560))
    core.lineToPoint_(NSMakePoint(404, 470))
    core.lineToPoint_(NSMakePoint(300, 424))
    core.setLineWidth_(17)
    core.setLineCapStyle_(1)
    core.setLineJoinStyle_(1)
    NSColor.colorWithSRGBRed_green_blue_alpha_(1.0, 0.90, 0.55, 0.95).setStroke()
    core.stroke()

    # 几道暗裂隙
    for crack in ([(360, 690), (432, 640), (392, 566)],
                  [(470, 690), (520, 660)]):
        cr = NSBezierPath.bezierPath()
        cr.moveToPoint_(NSMakePoint(*crack[0]))
        for p in crack[1:]:
            cr.lineToPoint_(NSMakePoint(*p))
        cr.setLineWidth_(7)
        cr.setLineCapStyle_(1)
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.05, 0.03, 0.0, 0.22).setStroke()
        cr.stroke()

    NSGraphicsContext.restoreGraphicsState()


def render(path):
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, int(SIZE), int(SIZE), 8, 4, True, False, "NSCalibratedRGBColorSpace", 0, 0)
    ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(ctx)
    draw_background()
    draw_ore()
    NSGraphicsContext.restoreGraphicsState()
    data = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, None)
    ok = data.writeToFile_atomically_(path, True)
    print("icon 1024 ->", path, ok)


def build_icns():
    os.makedirs(ICONSET, exist_ok=True)
    specs = [(16, "icon_16x16"), (32, "icon_16x16@2x"), (32, "icon_32x32"),
             (64, "icon_32x32@2x"), (128, "icon_128x128"), (256, "icon_128x128@2x"),
             (256, "icon_256x256"), (512, "icon_256x256@2x"), (512, "icon_512x512"),
             (1024, "icon_512x512@2x")]
    for px, name in specs:
        out = os.path.join(ICONSET, name + ".png")
        subprocess.run(["sips", "-z", str(px), str(px), OUT_PNG, "--out", out],
                       check=True, capture_output=True)
    subprocess.run(["iconutil", "-c", "icns", ICONSET, "-o", OUT_ICNS],
                   check=True, capture_output=True)
    print("icns ->", OUT_ICNS, os.path.getsize(OUT_ICNS), "bytes")


if __name__ == "__main__":
    __import__("AppKit").NSApplication.sharedApplication()
    render(OUT_PNG)
    build_icns()
