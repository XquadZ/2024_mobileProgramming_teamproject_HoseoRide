import 'package:flutter/material.dart';

import 'core/router.dart';
import 'core/theme.dart';

class App extends StatelessWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: '호서대 셔틀버스',
      theme: appTheme,
      darkTheme: appThemeDark,
      routerConfig: router,
      debugShowCheckedModeBanner: false,
    );
  }
}
