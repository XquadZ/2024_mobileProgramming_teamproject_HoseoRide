class Schedule {
  final int id;
  final int routeId;
  final String routeName;
  final String departureTime;
  final String dayType;

  const Schedule({
    required this.id,
    required this.routeId,
    required this.routeName,
    required this.departureTime,
    required this.dayType,
  });

  factory Schedule.fromJson(Map<String, dynamic> json) {
    return Schedule(
      id: json['id'] as int,
      routeId: json['route_id'] as int? ?? 0,
      routeName: json['route_name'] as String? ?? '',
      departureTime: json['departure_time'] as String,
      dayType: json['day_type'] as String? ?? 'weekday',
    );
  }
}
