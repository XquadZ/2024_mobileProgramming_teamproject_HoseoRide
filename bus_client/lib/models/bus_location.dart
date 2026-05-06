class BusLocation {
  final double latitude;
  final double longitude;
  final double confidence;
  final int routeId;
  final String tripId;
  final DateTime updatedAt;

  const BusLocation({
    required this.latitude,
    required this.longitude,
    required this.confidence,
    required this.routeId,
    required this.tripId,
    required this.updatedAt,
  });

  factory BusLocation.fromJson(Map<String, dynamic> json) {
    return BusLocation(
      latitude: (json['latitude'] as num).toDouble(),
      longitude: (json['longitude'] as num).toDouble(),
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0.0,
      routeId: json['route_id'] as int? ?? 0,
      tripId: json['trip_id'] as String? ?? '',
      updatedAt: json['updated_at'] != null
          ? DateTime.parse(json['updated_at'] as String)
          : DateTime.now(),
    );
  }
}
