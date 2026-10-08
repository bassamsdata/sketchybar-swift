#!/usr/bin/perl
# Text width (pt) — 12pt monospace 7.2, Hangul/Han 10.375 (measured) (same values as fit.pl). perl width.pl "text"
use utf8; use strict; binmode STDOUT, ':utf8';
my $t = shift // ''; utf8::decode($t); my $w = 0;
$w += ($_ =~ /[\p{Hangul}\p{Han}\p{Hiragana}\p{Katakana}]/ ? 10.375 : 7.2) for split //, $t;
printf "%d\n", $w + 0.999;
