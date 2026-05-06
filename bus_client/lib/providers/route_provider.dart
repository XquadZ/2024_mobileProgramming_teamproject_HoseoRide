import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/shuttle_route.dart';
import 'bus_location_provider.dart';

final routeListProvider = FutureProvider.autoDispose<List<ShuttleRoute>>((ref) {
  final api = ref.read(apiServiceProvider);
  return api.getRoutes();
});

final routeDetailProvider = FutureProvider.autoDispose.family<ShuttleRoute, int>((ref, routeId) {
  final api = ref.read(apiServiceProvider);
  return api.getRoute(routeId);
});
