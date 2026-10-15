// JSON menu snapshots and explicit, bounds-checked Accessibility actions.
import AppKit
import ApplicationServices

func emit(_ value: Any) {
  if let data = try? JSONSerialization.data(withJSONObject: value) {
    FileHandle.standardOutput.write(data)
  }
}
func attr(_ e: AXUIElement, _ name: String) -> AnyObject? {
  var value: AnyObject?
  return AXUIElementCopyAttributeValue(e, name as CFString, &value) == .success ? value : nil
}
func kids(_ e: AXUIElement) -> [AXUIElement] {
  (attr(e, kAXChildrenAttribute) as? [AXUIElement]) ?? []
}
func title(_ e: AXUIElement) -> String { (attr(e, kAXTitleAttribute) as? String) ?? "" }
func menus(_ pid: pid_t) -> [AXUIElement] {
  guard let bar = attr(AXUIElementCreateApplication(pid), kAXMenuBarAttribute) else { return [] }
  return kids(bar as! AXUIElement)
}
func items(_ m: AXUIElement) -> [AXUIElement] { kids(m).first.map(kids) ?? [] }

let args = CommandLine.arguments
guard args.count >= 2 else { exit(2) }
if args[1] == "front" {
  if let app = NSWorkspace.shared.frontmostApplication {
    emit(["pid": Int(app.processIdentifier), "name": app.localizedName ?? "?"])
  } else { emit([String: String]()) }
  exit(0)
}
guard args.count >= 3, let pid = pid_t(args[2]), pid > 0, AXIsProcessTrusted() else { emit([]); exit(1) }
let top = menus(pid)
switch args[1] {
case "menus":
  var rows: [[String: Any]] = []
  for (index, menu) in top.enumerated() where index >= 2 {
    let entries = items(menu).enumerated().compactMap { i, item -> [String: Any]? in
      let name = title(item)
      if name.isEmpty { return nil }
      return ["index": i, "title": name,
              "enabled": (attr(item, kAXEnabledAttribute) as? Bool) ?? false,
              "shortcut": (attr(item, "AXMenuItemCmdChar") as? String) ?? ""]
    }
    rows.append(["menu": index, "title": title(menu), "items": entries])
  }
  emit(rows)
case "settings":
  guard top.count > 1 else { exit(1) }
  for item in items(top[1]) where ["Settings…", "Preferences…", "설정…", "환경설정…"].contains(title(item)) {
    exit(AXUIElementPerformAction(item, kAXPressAction as CFString) == .success ? 0 : 1)
  }
  exit(1)
case "press":
  guard args.count == 5, let menu = Int(args[3]), let index = Int(args[4]),
        menu >= 2, menu < top.count, index >= 0 else { exit(2) }
  let entries = items(top[menu])
  guard index < entries.count else { exit(2) }
  exit(AXUIElementPerformAction(entries[index], kAXPressAction as CFString) == .success ? 0 : 1)
default: exit(2)
}
