// Emit one line for an outside click. No command argument or shell execution.
import AppKit
import Darwin

func insideBar(_ point: CGPoint) -> Bool {
  let list = CGWindowListCopyWindowInfo(.optionOnScreenOnly, kCGNullWindowID) as? [[String: Any]] ?? []
  return list.contains { window in
    guard (window[kCGWindowOwnerName as String] as? String) == "sketchybar",
          let bounds = window[kCGWindowBounds as String] as? NSDictionary,
          let rect = CGRect(dictionaryRepresentation: bounds) else { return false }
    return rect.contains(point)
  }
}
NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown]) { _ in
  let mouse = NSEvent.mouseLocation
  let height = NSScreen.screens.first?.frame.height ?? 0
  if !insideBar(CGPoint(x: mouse.x, y: height - mouse.y)) {
    print("outside"); fflush(stdout); exit(0)
  }
}
DispatchQueue.main.asyncAfter(deadline: .now() + 600) { exit(0) }
NSApplication.shared.setActivationPolicy(.prohibited)
NSApplication.shared.run()
