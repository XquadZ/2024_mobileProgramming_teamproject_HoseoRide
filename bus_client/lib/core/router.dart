import 'package:go_router/go_router.dart';

import '../screens/home_screen.dart';
import '../screens/route_detail_screen.dart';
import '../screens/route_list_screen.dart';
import '../screens/schedule_screen.dart';

final router = GoRouter(
  initialLocation: '/',
  routes: [
    GoRoute(
      path: '/',
      builder: (context, state) => const HomeScreen(),
    ),
    GoRoute(
      path: '/routes',
      builder: (context, state) => const RouteListScreen(),
    ),
    GoRoute(
      path: '/routes/:routeId',
      builder: (context, state) {
        final routeId = int.parse(state.pathParameters['routeId']!);
        return RouteDetailScreen(routeId: routeId);
      },
    ),
    GoRoute(
      path: '/schedule',
      builder: (context, state) => const ScheduleScreen(),
    ),
  ],
);
