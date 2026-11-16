import Foundation
import Vision
import AppKit
// archivo puntuacionEstetica(-1..1) esUtilitaria
if #available(macOS 15.0, *) {
  for ruta in CommandLine.arguments.dropFirst() {
    guard let img = NSImage(contentsOfFile: ruta), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    let req = CalculateImageAestheticsScoresRequest()
    let sem = DispatchSemaphore(value: 0)
    Task {
      if let r = try? await req.perform(on: cg) { print(ruta, String(format: "%.4f", r.overallScore), r.isUtility) } else { print(ruta, "error") }
      sem.signal()
    }
    sem.wait()
  }
}
