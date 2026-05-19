#pragma once

#include <Arduino.h>

#include "tof_scan.h"

namespace stranger {

enum class ObstacleKind {
  Clear,
  SlowZone,
  ObstacleStop,
  SensorFault,
};

struct ObstacleState {
  ObstacleKind kind = ObstacleKind::SensorFault;
  bool avoidanceEnabled = true;
  bool frontLeftOk = false;
  bool frontRightOk = false;
  uint16_t frontLeftMm = 0;
  uint16_t frontRightMm = 0;
  uint16_t frontMinMm = 0;
  int suggestedTurn = 0;
  const char *reason = "boot";
  uint32_t updatedAtMs = 0;
};

struct GateDecision {
  bool allowed = true;
  bool adjusted = false;
  int throttle = 0;
  int turn = 0;
  ObstacleKind state = ObstacleKind::Clear;
  const char *reason = "clear";
};

class ObstacleGate {
 public:
  explicit ObstacleGate(TofScanner &tof);

  void update();
  GateDecision apply(int throttle, int turn, bool allowEscape = false) const;

  void setEnabled(bool enabled);
  bool enabled() const;
  const ObstacleState &state() const;
  const char *stateName() const;
  const char *stateName(ObstacleKind kind) const;
  void printState(Stream &out) const;

 private:
  bool usableFrontSample(uint8_t index, uint16_t &distanceMm) const;
  int computeSuggestedTurn(uint16_t frontLeftMm, uint16_t frontRightMm) const;

  TofScanner &tof_;
  bool enabled_ = true;
  ObstacleState state_;
};

}  // namespace stranger
