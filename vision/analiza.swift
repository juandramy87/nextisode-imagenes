import Foundation
import Vision
import AppKit
// Salida JSON por línea: archivo, w, h, caras [{x,y,w,h}], textos [{t, area}]
for ruta in CommandLine.arguments.dropFirst() {
  guard let img = NSImage(contentsOfFile: ruta), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
  let caras = VNDetectFaceRectanglesRequest()
  let texto = VNRecognizeTextRequest(); texto.recognitionLevel = .accurate; texto.usesLanguageCorrection = false
  try? VNImageRequestHandler(cgImage: cg).perform([caras, texto])
  let cs = (caras.results ?? []).map { ["x": $0.boundingBox.midX, "y": 1 - $0.boundingBox.midY, "w": $0.boundingBox.width, "h": $0.boundingBox.height] }
  let ts = (texto.results ?? []).compactMap { o -> [String: Any]? in
    guard let s = o.topCandidates(1).first, s.confidence > 0.3 else { return nil }
    return ["t": s.string, "area": Double(o.boundingBox.width * o.boundingBox.height), "y": Double(1 - o.boundingBox.midY)]
  }
  let d: [String: Any] = ["archivo": (ruta as NSString).lastPathComponent, "w": cg.width, "h": cg.height, "caras": cs, "textos": ts]
  if let j = try? JSONSerialization.data(withJSONObject: d), let s = String(data: j, encoding: .utf8) { print(s) }
}
