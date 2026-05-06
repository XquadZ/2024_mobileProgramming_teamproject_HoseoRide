import 'package:dio/dio.dart';

import '../core/constants.dart';
import '../models/bus_location.dart';
import '../models/schedule.dart';
import '../models/shuttle_route.dart';

class ApiService {
  final Dio _dio;

  ApiService() : _dio = Dio(BaseOptions(baseUrl: apiBaseUrl, connectTimeout: const Duration(seconds: 10)));

  Future<List<ShuttleRoute>> getRoutes() async {
    final response = await _dio.get('/routes');
    final data = response.data as List<dynamic>;
    return data.map((json) => ShuttleRoute.fromJson(json as Map<String, dynamic>)).toList();
  }

  Future<ShuttleRoute> getRoute(int routeId) async {
    final response = await _dio.get('/routes/$routeId');
    return ShuttleRoute.fromJson(response.data as Map<String, dynamic>);
  }

  Future<List<Schedule>> getSchedules({String dayType = 'weekday'}) async {
    final response = await _dio.get('/schedules', queryParameters: {'day_type': dayType});
    final data = response.data as List<dynamic>;
    return data.map((json) => Schedule.fromJson(json as Map<String, dynamic>)).toList();
  }

  Future<List<Schedule>> getRouteSchedules(int routeId) async {
    final response = await _dio.get('/routes/$routeId/schedules');
    final data = response.data as List<dynamic>;
    return data.map((json) => Schedule.fromJson(json as Map<String, dynamic>)).toList();
  }

  Future<List<BusLocation>> getBusLocations() async {
    final response = await _dio.get('/buses/location');
    final data = response.data as List<dynamic>;
    return data.map((json) => BusLocation.fromJson(json as Map<String, dynamic>)).toList();
  }

  Future<List<BusLocation>> getRouteBusLocations(int routeId) async {
    final response = await _dio.get('/buses/location/$routeId');
    final data = response.data as List<dynamic>;
    return data.map((json) => BusLocation.fromJson(json as Map<String, dynamic>)).toList();
  }
}
