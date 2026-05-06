import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/schedule.dart';
import 'bus_location_provider.dart';

final scheduleListProvider = FutureProvider.autoDispose.family<List<Schedule>, String>((ref, dayType) {
  final api = ref.read(apiServiceProvider);
  return api.getSchedules(dayType: dayType);
});

final routeScheduleProvider = FutureProvider.autoDispose.family<List<Schedule>, int>((ref, routeId) {
  final api = ref.read(apiServiceProvider);
  return api.getRouteSchedules(routeId);
});
