import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../core/constants.dart';
import '../models/bus_location.dart';

class WebSocketService {
  WebSocketChannel? _channel;
  final _locationController = StreamController<BusLocation>.broadcast();
  Timer? _reconnectTimer;
  int? _currentRouteId;

  Stream<BusLocation> get locationStream => _locationController.stream;

  void connect({int? routeId}) {
    _currentRouteId = routeId;
    _doConnect();
  }

  void _doConnect() {
    _channel?.sink.close();

    final path = _currentRouteId != null ? '/location/$_currentRouteId' : '/location';
    final uri = Uri.parse('$wsBaseUrl$path');
    _channel = WebSocketChannel.connect(uri);

    _channel!.stream.listen(
      (data) {
        final json = jsonDecode(data as String) as Map<String, dynamic>;
        if (json['type'] == 'ping') return;
        _locationController.add(BusLocation.fromJson(json));
      },
      onError: (error) {
        _scheduleReconnect();
      },
      onDone: () {
        _scheduleReconnect();
      },
    );
  }

  void _scheduleReconnect() {
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 3), _doConnect);
  }

  void disconnect() {
    _reconnectTimer?.cancel();
    _channel?.sink.close();
    _channel = null;
  }

  void dispose() {
    disconnect();
    _locationController.close();
  }
}
