// On-demand Wi-Fi scanning. SSIDs are returned as JSON, never cached on disk.
import AppKit
import CoreLocation
import CoreWLAN

func emit(_ value: Any) {
  if let data = try? JSONSerialization.data(withJSONObject: value) {
    FileHandle.standardOutput.write(data)
  }
}
final class Scanner: NSObject, CLLocationManagerDelegate {
  let manager = CLLocationManager()
  func start() { manager.delegate = self; check() }
  func check() {
    switch manager.authorizationStatus {
    case .authorizedAlways, .authorized: scan()
    case .notDetermined: manager.requestWhenInUseAuthorization()
    default: emit(["status": "denied", "networks": []] as [String: Any]); exit(0)
    }
  }
  func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
    if manager.authorizationStatus != .notDetermined { check() }
  }
  func scan() {
    var best: [String: Int] = [:]
    if let interface = CWWiFiClient.shared().interface(),
       let networks = try? interface.scanForNetworks(withSSID: nil) {
      for network in networks {
        if let ssid = network.ssid { best[ssid] = max(best[ssid] ?? -999, network.rssiValue) }
      }
    }
    let rows = best.sorted { $0.value > $1.value }.map {
      ["ssid": $0.key, "rssi": $0.value] as [String: Any]
    }
    emit(["status": "ok", "networks": rows]); exit(0)
  }
}
let scanner = Scanner()
DispatchQueue.main.async { scanner.start() }
DispatchQueue.main.asyncAfter(deadline: .now() + 30) {
  emit(["status": "undetermined", "networks": []] as [String: Any]); exit(0)
}
NSApplication.shared.setActivationPolicy(.prohibited)
NSApplication.shared.run()
