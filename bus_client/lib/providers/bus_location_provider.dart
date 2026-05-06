import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/bus_location.dart';
import '../services/api_service.dart';
import '../services/websocket_service.dart';

final apiServiceProvider = Provider((ref) => ApiService());

final wsServiceProvider = Provider((ref) {
  final ws = WebSocketService();
  ref.onDispose(() => ws.dispose());
  return ws;
});

final busLocationsProvider = StreamProvider.autoDispose<List<BusLocation>>((ref) {
  final api = ref.read(apiServiceProvider);
  final ws = ref.read(wsServiceProvider);
  ws.connect();

  final controller = StreamController<List<BusLocation>>();
  final locations = <String, BusLocation>{};

  // Initial fetch
  api.getBusLocations().then((list) {
    for (final loc in list) {
      locations[loc.tripId] = loc;
    }
    controller.add(locations.values.toList());
  });

  // Live updates
  final sub = ws.locationStream.listen((loc) {
    locations[loc.tripId] = loc;
    controller.add(locations.values.toList());
  });

  ref.onDispose(() {
    sub.cancel();
    controller.close();
  });

  return controller.stream;
});
