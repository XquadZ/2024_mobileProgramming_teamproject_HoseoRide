import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/schedule_provider.dart';

class ScheduleScreen extends ConsumerStatefulWidget {
  const ScheduleScreen({super.key});

  @override
  ConsumerState<ScheduleScreen> createState() => _ScheduleScreenState();
}

class _ScheduleScreenState extends ConsumerState<ScheduleScreen> {
  String _selectedDayType = 'weekday';

  @override
  Widget build(BuildContext context) {
    final schedules = ref.watch(scheduleListProvider(_selectedDayType));

    return Scaffold(
      appBar: AppBar(title: const Text('운행 시간표')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'weekday', label: Text('평일')),
                ButtonSegment(value: 'saturday', label: Text('토요일')),
                ButtonSegment(value: 'holiday', label: Text('공휴일')),
              ],
              selected: {_selectedDayType},
              onSelectionChanged: (val) {
                setState(() => _selectedDayType = val.first);
              },
            ),
          ),
          Expanded(
            child: schedules.when(
              data: (list) {
                if (list.isEmpty) {
                  return const Center(child: Text('해당 요일에 운행 시간표가 없습니다'));
                }

                // Group by route name
                final grouped = <String, List<dynamic>>{};
                for (final s in list) {
                  grouped.putIfAbsent(s.routeName, () => []).add(s);
                }

                return ListView(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  children: grouped.entries.map((entry) {
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Padding(
                          padding: const EdgeInsets.only(top: 16, bottom: 8),
                          child: Text(
                            entry.key,
                            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                  fontWeight: FontWeight.bold,
                                ),
                          ),
                        ),
                        Wrap(
                          spacing: 8,
                          runSpacing: 4,
                          children: entry.value.map((s) {
                            return Chip(
                              label: Text(s.departureTime),
                              visualDensity: VisualDensity.compact,
                            );
                          }).toList(),
                        ),
                        const Divider(),
                      ],
                    );
                  }).toList(),
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
}
