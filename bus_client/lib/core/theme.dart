import 'package:flutter/material.dart';

final appTheme = ThemeData(
  colorSchemeSeed: const Color(0xFF1976D2),
  useMaterial3: true,
  brightness: Brightness.light,
  appBarTheme: const AppBarTheme(centerTitle: true),
);

final appThemeDark = ThemeData(
  colorSchemeSeed: const Color(0xFF1976D2),
  useMaterial3: true,
  brightness: Brightness.dark,
  appBarTheme: const AppBarTheme(centerTitle: true),
);
