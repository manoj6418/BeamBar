// Draws the BeamBar icon (1024 and 512) and the GitHub social preview (1280x640).
// Run: swift assets/make-logo.swift assets
import AppKit

let out = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "assets"

func color(_ hex: UInt32, _ a: CGFloat = 1) -> NSColor {
    NSColor(srgbRed: CGFloat((hex >> 16) & 0xFF) / 255, green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255, alpha: a)
}
let space = CGColorSpace(name: CGColorSpace.sRGB)!
let cyan = color(0x5EE7FF), violet = color(0x8B7CFF)

/// Projector on the left throwing a beam onto a screen, inside a dark macOS tile.
func drawMark(in ctx: CGContext, origin: CGPoint, size: CGFloat) {
    let s = size / 1024
    func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: origin.x + x * s, y: origin.y + y * s) }
    func r(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat) -> CGRect { CGRect(x: origin.x + x * s, y: origin.y + y * s, width: w * s, height: h * s) }

    // Tile.
    let tile = CGPath(roundedRect: r(100, 100, 824, 824), cornerWidth: 185 * s, cornerHeight: 185 * s, transform: nil)
    ctx.saveGState()
    ctx.setShadow(offset: CGSize(width: 0, height: -12 * s), blur: 30 * s, color: color(0, 0.35).cgColor)
    ctx.addPath(tile); ctx.setFillColor(color(0x12162A).cgColor); ctx.fillPath()
    ctx.restoreGState()
    ctx.saveGState()
    ctx.addPath(tile); ctx.clip()
    let bg = CGGradient(colorsSpace: space, colors: [color(0x1E2445).cgColor, color(0x0C0E1C).cgColor] as CFArray, locations: [0, 1])!
    ctx.drawLinearGradient(bg, start: p(512, 924), end: p(512, 100), options: [])

    // Screen on the right.
    let screen = CGPath(roundedRect: r(620, 330, 220, 360), cornerWidth: 26 * s, cornerHeight: 26 * s, transform: nil)
    ctx.saveGState()
    ctx.setShadow(offset: .zero, blur: 60 * s, color: cyan.withAlphaComponent(0.55).cgColor)
    ctx.addPath(screen); ctx.setFillColor(color(0xE9FBFF, 0.95).cgColor); ctx.fillPath()
    ctx.restoreGState()

    // Beam from the lens to the screen.
    let beam = CGMutablePath()
    beam.move(to: p(318, 532)); beam.addLine(to: p(622, 690)); beam.addLine(to: p(622, 330)); beam.addLine(to: p(318, 492)); beam.closeSubpath()
    ctx.saveGState()
    ctx.addPath(beam); ctx.clip()
    let light = CGGradient(colorsSpace: space, colors: [cyan.withAlphaComponent(0.85).cgColor, violet.withAlphaComponent(0.25).cgColor] as CFArray, locations: [0, 1])!
    ctx.drawLinearGradient(light, start: p(318, 512), end: p(622, 512), options: [])
    ctx.restoreGState()

    // Projector body and lens.
    let body = CGPath(roundedRect: r(170, 418, 200, 188), cornerWidth: 44 * s, cornerHeight: 44 * s, transform: nil)
    ctx.addPath(body)
    let bodyGradient = CGGradient(colorsSpace: space, colors: [color(0xF3F4FA).cgColor, color(0xB9BED3).cgColor] as CFArray, locations: [0, 1])!
    ctx.saveGState(); ctx.addPath(body); ctx.clip()
    ctx.drawLinearGradient(bodyGradient, start: p(270, 606), end: p(270, 418), options: [])
    ctx.restoreGState()
    ctx.addEllipse(in: r(282, 470, 84, 84)); ctx.setFillColor(color(0x1B2040).cgColor); ctx.fillPath()
    ctx.saveGState()
    ctx.setShadow(offset: .zero, blur: 22 * s, color: cyan.cgColor)
    ctx.addEllipse(in: r(300, 488, 48, 48)); ctx.setFillColor(cyan.cgColor); ctx.fillPath()
    ctx.restoreGState()
    ctx.restoreGState()
}

func render(_ width: Int, _ height: Int, _ name: String, _ draw: (CGContext) -> Void) {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height, bitsPerSample: 8,
                               samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
                               bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    draw(NSGraphicsContext.current!.cgContext)
    NSGraphicsContext.restoreGraphicsState()
    try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: "\(out)/\(name)"))
    print("wrote \(out)/\(name)")
}

render(1024, 1024, "icon-1024.png") { drawMark(in: $0, origin: .zero, size: 1024) }
render(512, 512, "icon-512.png") { drawMark(in: $0, origin: .zero, size: 512) }
render(1280, 640, "social-preview.png") { ctx in
    let bg = CGGradient(colorsSpace: space, colors: [color(0x1A2040).cgColor, color(0x090B16).cgColor] as CFArray, locations: [0, 1])!
    ctx.drawLinearGradient(bg, start: CGPoint(x: 0, y: 640), end: CGPoint(x: 1280, y: 0), options: [])
    drawMark(in: ctx, origin: CGPoint(x: 40, y: 80), size: 480)
    NSAttributedString(string: "BeamBar", attributes: [.font: NSFont.systemFont(ofSize: 92, weight: .bold),
                                                       .foregroundColor: NSColor.white]).draw(at: CGPoint(x: 560, y: 345))
    NSAttributedString(string: "A Mac menu bar remote for Google TV and\nAndroid TV projectors and TVs.", attributes: [
        .font: NSFont.systemFont(ofSize: 34), .foregroundColor: NSColor.white.withAlphaComponent(0.72)])
        .draw(in: CGRect(x: 562, y: 200, width: 690, height: 120))
    NSAttributedString(string: "Floating remote · CLI · phone remote · hotkeys · scenes", attributes: [
        .font: NSFont.systemFont(ofSize: 24, weight: .medium), .foregroundColor: cyan]).draw(at: CGPoint(x: 562, y: 150))
}
