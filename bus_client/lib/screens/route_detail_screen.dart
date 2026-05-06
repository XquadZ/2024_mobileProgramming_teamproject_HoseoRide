import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/route_provider.dart';
import '../providers/schedule_provider.dart';

class RouteDetailScreen extends ConsumerWidget {
  final int routeId;

  const RouteDetailScreen({super.key, required this.routeId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final routeAsync = ref.watch(routeDetailProvider(routeId));
    final schedulesAsync = ref.watch(routeScheduleProvider(routeId));

    return Scaffold(
      appBar: AppBar(
        title: routeAsync.when(
          data: (route) => Text(route.name),
          loading: () => const Text('로딩...'),
          error: (_, _) => const Text('노선 상세'),
        ),
      ),
      body: Column(
        children: [
          // Route map placeholder
          Expanded(
            flex: 2,
            child: Container(
              color: Colors.grey[200],
              child: Center(
                child: routeAsync.when(
                  data: (route) => Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.map, size: 48, color: Colors.grey[400]),
                      const SizedBox(height: 8),
                      Text(
                        '${route.name} 경로가 지도에 표시됩니다',
                        style: TextStyle(color: Colors.grey[600]),
                      ),
                      Text(
                        '경유지 ${route.waypoints.length}개',
                        style: TextStyle(color: Colors.grey[500], fontSize: 12),
                      ),
                    ],
                  ),
                  loading: () => const CircularProgressIndicator(),
                  error: (e, _) => Text('$e'),
                ),
              ),
            ),
          ),

          // Schedule list
          Expanded(
            flex: 2,
            child: schedulesAsync.when(
              data: (schedules) {
                if (schedules.isEmpty) {
                  return const Center(child: Text('등록된 시간표가 없습니다'));
                }
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
                      child: Text(
                        '운행 시간표',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                    ),
                    Expanded(
                      child: ListView.builder(
                        padding: const EdgeInsets.symmetric(horizontal: 16),
                        itemCount: schedules.length,
                        itemBuilder: (context, index) {
                          final s = schedules[index];
                          return ListTile(
                            dense: true,
                            leading: const Icon(Icons.access_time, size: 20),
                            title: Text(s.departureTime),
                            subtitle: Text(_dayTypeLabel(s.dayType)),
                          );
                        },
                      ),
                    ),
                  ],
                );
              },
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(child: Text('시간표 로드 실패: $e')),
            ),
          ),
        ],
      ),
    );
  }

  String _dayTypeLabel(String dayType) {
    switch (dayType) {
      case 'weekday':
        return '평일';
      case 'saturday':
        return '토요일';
      case 'holiday':
        return '공휴일';
      default:
        return dayType;
    }
  }
}
