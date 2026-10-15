// Local SVG icons and bounded popup rows. JSON is data; no shell or web access.
import AppKit
import Darwin

func color(_ hex: String) -> NSColor {
  let value = UInt32(hex.replacingOccurrences(of: "0x", with: ""), radix: 16) ?? 0xffe6ebe6
  return NSColor(red: CGFloat((value >> 16) & 255) / 255,
                 green: CGFloat((value >> 8) & 255) / 255,
                 blue: CGFloat(value & 255) / 255, alpha: CGFloat(value >> 24) / 255)
}
func writePNG(_ rep: NSBitmapImageRep, _ path: String) throws {
  let fd = open(path, O_WRONLY | O_CREAT | O_NOFOLLOW | O_NONBLOCK, 0o600)
  guard fd >= 0 else { throw NSError(domain: "private image", code: 1) }
  defer { close(fd) }
  var info = stat()
  guard fstat(fd, &info) == 0, info.st_uid == getuid(), (info.st_mode & S_IFMT) == S_IFREG else {
    throw NSError(domain: "private image", code: 2)
  }
  guard fchmod(fd, 0o600) == 0, ftruncate(fd, 0) == 0,
        let data = rep.representation(using: .png, properties: [:]) else {
    throw NSError(domain: "private image", code: 3)
  }
  try FileHandle(fileDescriptor: fd, closeOnDealloc: false).write(contentsOf: data)
}
func bitmap(_ width: Int, _ height: Int, _ draw: () -> Void) -> NSBitmapImageRep {
  let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: width * 2, pixelsHigh: height * 2,
                            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                            colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
  NSGraphicsContext.saveGraphicsState()
  let context = NSGraphicsContext(bitmapImageRep: rep)!
  NSGraphicsContext.current = context
  context.cgContext.scaleBy(x: 2, y: 2)
  draw()
  NSGraphicsContext.restoreGraphicsState()
  return rep
}
func font(_ family: String, _ size: CGFloat, _ bold: Bool = false) -> NSFont {
  return NSFontManager.shared.font(withFamily: family, traits: bold ? .boldFontMask : [],
                                   weight: bold ? 9 : 5, size: size)
    ?? NSFont.monospacedSystemFont(ofSize: size, weight: bold ? .bold : .regular)
}
func text(_ value: String, _ x: CGFloat, _ width: CGFloat, _ height: CGFloat,
          _ face: NSFont, _ tint: NSColor, _ align: String = "left") {
  guard width > 0 else { return }
  let attrs: [NSAttributedString.Key: Any] = [.font: face, .foregroundColor: tint]
  var value = value
  if (value as NSString).size(withAttributes: attrs).width > width {
    while !value.isEmpty && ((value + "…") as NSString).size(withAttributes: attrs).width > width { value.removeLast() }
    value += "…"
  }
  let size = (value as NSString).size(withAttributes: attrs)
  let offset = align == "right" ? width - size.width : align == "center" ? (width - size.width) / 2 : 0
  NSGraphicsContext.saveGraphicsState()
  NSBezierPath(rect: NSRect(x: x, y: 0, width: width, height: height)).addClip()
  (value as NSString).draw(at: NSPoint(x: x + max(0, offset), y: (height - size.height) / 2), withAttributes: attrs)
  NSGraphicsContext.restoreGraphicsState()
}
func image(_ path: String, _ rect: NSRect) {
  if let image = NSImage(contentsOfFile: path) { image.draw(in: rect) }
}
let args = CommandLine.arguments
if args.count == 6 && args[1] == "icons" {
  for (name, tint) in [("openai", args[4]), ("claude", "0xffd97757"), ("mute", args[5]), ("laptop", args[4]), ("headphones", args[5]), ("wifi", args[4]), ("wifi-outline", args[5])] {
    let rep = bitmap(16, 16) {
      image(args[2] + "/" + name + ".svg", NSRect(x: 0, y: 0, width: 16, height: 16))
      color(tint).setFill()
      NSRect(x: 0, y: 0, width: 16, height: 16).fill(using: .sourceIn)
    }
    do { try writePNG(rep, args[3] + "/" + name + ".png") } catch { exit(1) }
  }
  exit(0)
}
guard args.count == 4, args[1] == "rows", args[3].range(of: "^[a-z0-9-]+$", options: .regularExpression) != nil else { exit(1) }
let input = FileHandle.standardInput.readDataToEndOfFile()
guard input.count <= 262144,
      let payload = try? JSONSerialization.jsonObject(with: input) as? [String: Any],
      let rows = payload["rows"] as? [[String: Any]], rows.count <= 40 else { exit(1) }
let width = min(1200, max(100, payload["width"] as? Int ?? 261))
let size = min(24, max(9, payload["font_size"] as? Double ?? 12))
let family = payload["font"] as? String ?? "JetBrains Mono"
let palette = payload["palette"] as? [String: String] ?? [:]
func token(_ name: String) -> NSColor { color(palette[name] ?? "0xffe6ebe6") }
var paths: [String] = []
for (index, row) in rows.enumerated() {
  let height = min(160, max(1, row["height"] as? Int ?? 24))
  let h = CGFloat(height), w = CGFloat(width), scale = CGFloat(size / 12)
  let kind = row["kind"] as? String ?? "text"
  let rep = bitmap(width, height) {
    let label = row["label"] as? String ?? ""
    let left = row["left"] as? String ?? ""
    let right = row["right"] as? String ?? ""
    let key = CGFloat(row["key_width"] as? Double ?? 52) * scale
    let pad = 12 * scale
    let face = font(family, CGFloat(size), row["bold"] as? Bool ?? false)
    let main = row["color"].flatMap { $0 as? String }.map(color) ?? token("text")
    if kind == "title" || kind == "section" {
      text(label, pad, w - 2 * pad, h, font(family, CGFloat(size - 1), true), token("muted"))
    } else if kind == "gauge" {
      let start = pad + key, available = w - start - pad
      let value = min(100, max(0, row["percent"] as? Double ?? 0))
      let cell = available / 50, gap = min(1.3 * scale, cell / 3)
      for i in 0..<50 {
        (Double(i) < value / 2 ? main : token("line")).setFill()
        NSRect(x: start + CGFloat(i) * cell, y: (h - 10 * scale) / 2,
               width: max(0, cell - gap), height: 10 * scale).fill()
      }
    } else if kind == "calendar" {
      let cells = row["cells"] as? [[String: Any]] ?? []
      let cell = (w - 2 * pad) / 7
      for (i, cellData) in cells.prefix(7).enumerated() {
        let tint = color(cellData["color"] as? String ?? palette["text"] ?? "0xffe6ebe6")
        text(cellData["label"] as? String ?? "", pad + CGFloat(i) * cell, cell, h, face, tint, "center")
      }
    } else if kind == "center" {
      text(label, pad, w - 2 * pad, h, face, main, "center")
      text(right, w - pad - 16 * scale, 16 * scale, h, face, token("dim"), "right")
    } else if kind == "image" {
      image(row["image"] as? String ?? "", NSRect(x: (w - 120) / 2, y: (h - 120) / 2, width: 120, height: 120))
    } else {
      let hasKey = !left.isEmpty || row["icon"] != nil || kind == "slider"
      let start = pad + (hasKey ? key : 0)
      let rightSize = (right as NSString).size(withAttributes: [.font: face]).width
      if let icon = row["icon"] as? String {
        image(icon, NSRect(x: pad, y: (h - 14 * scale) / 2, width: 14 * scale, height: 14 * scale))
      } else {
        text(left, pad, key - 4 * scale, h, face,
             color(row["left_color"] as? String ?? palette["dim"] ?? "0xff6b776f"))
      }
      if kind != "slider" {
        text(label, start, max(0, w - pad - start - (right.isEmpty ? 0 : rightSize + 12 * scale)), h, face, main,
             row["align"] as? String ?? "left")
      }
      text(right, w - pad - rightSize, rightSize, h, face,
           color(row["right_color"] as? String ?? palette["muted"] ?? "0xff8b968e"), "right")
    }
  }
  let path = args[2] + "/" + args[3] + "-" + String(index) + ".png"
  do { try writePNG(rep, path) } catch { exit(1) }
  paths.append(path)
}
if let output = try? JSONSerialization.data(withJSONObject: paths) { FileHandle.standardOutput.write(output) }
