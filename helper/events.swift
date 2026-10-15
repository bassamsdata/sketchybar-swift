// Calendar titles travel as JSON strings, never tab-separated commands.
import EventKit
import Foundation

func emit(_ value: Any) {
  if let data = try? JSONSerialization.data(withJSONObject: value) {
    FileHandle.standardOutput.write(data)
  }
}
let args = CommandLine.arguments
guard args.count >= 2 else { exit(2) }
let store = EKEventStore()
let granted = DispatchSemaphore(value: 0)
if EKEventStore.authorizationStatus(for: .event) == .notDetermined {
  store.requestFullAccessToEvents { _, _ in granted.signal() }
  _ = granted.wait(timeout: .now() + 30)
}
guard EKEventStore.authorizationStatus(for: .event) == .fullAccess else {
  emit(["error": "calendar_permission"]); exit(0)
}
let names: [String] = args.count > 2 ?
  ((try? JSONSerialization.jsonObject(with: Data(args[2].utf8))) as? [String] ?? []) : []
let calendars = names.isEmpty ? nil : store.calendars(for: .event).filter { names.contains($0.title) }
let calendar = Calendar.current, now = Date()
let day = DateFormatter(); day.dateFormat = "yyyy-MM-dd"
let start: Date
let end: Date
if args[1] == "today" {
  start = calendar.startOfDay(for: now)
  end = calendar.date(byAdding: .day, value: 1, to: start)!
} else {
  guard let date = day.date(from: args[1]),
        let next = calendar.date(byAdding: .month, value: 1, to: date) else { exit(2) }
  start = date; end = next
}
let date = DateFormatter(); date.dateFormat = args[1] == "today" ? "HH:mm" : "MM.dd"
let rows: [[String: Any]] = store.events(matching: store.predicateForEvents(
  withStart: start, end: end, calendars: calendars)).sorted { $0.startDate < $1.startDate }
  .filter { args[1] != "today" || (!$0.isAllDay && $0.endDate > now) }
  .map { event in
    ["date": date.string(from: event.startDate), "title": event.title ?? "",
     "calendar": event.calendar.title, "start": event.startDate.timeIntervalSince1970]
  }
emit(rows)
