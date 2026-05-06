import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../providers/route_provider.dart';

class RouteListScreen extends ConsumerWidget {
  const RouteListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final routes = ref.watch(routeListProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('셔틀 노선')),
      body: routes.when(
        data: (routeList) {
          if (routeList.isEmpty) {
            return const Center(child: Text('등록된 노선이 없습니다'));
          }
          return ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: routeList.length,
            separatorBuilder: (_, _) => const Divider(height: 1),
            itemBuilder: (context, index) {
              final route = routeList[index];
              return ListTile(
                leading: CircleAvatar(
                  backgroundColor: _parseColor(route.color),
                  child: const Icon(Icons.route, color: Colors.white),
                ),
                title: Text(route.name),
                subtitle: Text('${route.campus == "asan" ? "아산" : "천안"} 캠퍼스'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => context.push('/routes/${route.id}'),
              );
            },
          );
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('노선 로드 실패: $e')),
      ),
    );
  }

  Color _parseColor(String hex) {
    final code = hex.replaceFirst('#', '');
    return Color(int.parse('FF$code', radix: 16));
  }
}
