class ShuttleRoute {
  final int id;
  final String name;
  final String campus;
  final String direction;
  final String color;
  final List<List<double>> waypoints;

  const ShuttleRoute({
    required this.id,
    required this.name,
    required this.campus,
    required this.direction,
    required this.color,
    required this.waypoints,
  });

  factory ShuttleRoute.fromJson(Map<String, dynamic> json) {
    final rawWaypoints = json['waypoints'] as List<dynamic>? ?? [];
    return ShuttleRoute(
      id: json['id'] as int,
      name: json['name'] as String,
      campus: json['campus'] as String? ?? '',
      direction: json['direction'] as String? ?? '',
      color: json['color'] as String? ?? '#1976D2',
      waypoints: rawWaypoints
          .map((wp) => (wp as List<dynamic>).map((v) => (v as num).toDouble()).toList())
          .toList(),
    );
  }
}
