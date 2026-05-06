import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../providers/bus_location_provider.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final busLocations = ref.watch(busLocationsProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('호서대 셔틀버스'),
        actions: [
          IconButton(
            icon: const Icon(Icons.list),
            onPressed: () => context.push('/routes'),
            tooltip: '노선 목록',
          ),
          IconButton(
            icon: const Icon(Icons.schedule),
            onPressed: () => context.push('/schedule'),
            tooltip: '시간표',
          ),
        ],
      ),
      body: Column(
        children: [
          // Map placeholder — will be replaced with NaverMap
          Expanded(
            flex: 3,
            child: Container(
              color: Colors.grey[200],
              child: Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.map, size: 64, color: Colors.grey[400]),
                    const SizedBox(height: 16),
                    Text(
                      'Naver Map이 여기에 표시됩니다',
                      style: TextStyle(color: Colors.grey[600], fontSize: 16),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'NAVER_MAP_CLIENT_ID 설정 필요',
                      style: TextStyle(color: Colors.grey[500], fontSize: 12),
                    ),
                  ],
                ),
              ),
            ),
          ),

          // Bus status panel
          Expanded(
            flex: 1,
            child: busLocations.when(
              data: (locations) {
                if (locations.isEmpty) {
                  return const Center(
                    child: Text('현재 운행 중인 셔틀버스가 없습니다'),
                  );
                }
                return ListView.builder(
                  itemCount: locations.length,
                  itemBuilder: (context, index) {
                    final loc = locations[index];
                    return ListTile(
                      leading: Icon(
                        Icons.directions_bus,
                        color: loc.confidence > 0.7
                            ? Colors.green
                            : loc.confidence > 0.4
                                ? Colors.orange
                                : Colors.red,
                      ),
                      title: Text('노선 ${loc.routeId}'),
                      subtitle: Text(
                        '신뢰도 ${(loc.confidence * 100).toStringAsFixed(0)}% · '
                        '${_timeAgo(loc.updatedAt)}',
                      ),
                      trailing: Text(
                        '${loc.latitude.toStringAsFixed(4)}, ${loc.longitude.toStringAsFixed(4)}',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                      onTap: () => context.push('/routes/${loc.routeId}'),
                    );
                  },
                );
              },
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Icon(Icons.cloud_off, size: 48, color: Colors.grey),
                    const SizedBox(height: 8),
                    Text('서버 연결 실패', style: Theme.of(context).textTheme.bodyLarge),
                    const SizedBox(height: 4),
                    Text(
                      '백엔드 서버가 실행 중인지 확인하세요',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _timeAgo(DateTime dt) {
    final diff = DateTime.now().difference(dt);
    if (diff.inSeconds < 60) return '${diff.inSeconds}초 전';
    if (diff.inMinutes < 60) return '${diff.inMinutes}분 전';
    return '${diff.inHours}시간 전';
  }
}
