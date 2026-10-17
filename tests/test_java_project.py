"""Real multi-file javac parsing and project symbol/inheritance regressions."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.catalog_java import scan
from scripts import catalog_java

OVERRIDE = 'da653cb46db811eea68ffa163e0fa374'
HASHCODE = 'da74c9566db811eea68ffa163e0fa374'
SERIAL_UID = 'da6546306db811eea68ffa163e0fa374'
SYNC = 'da5de2b26db811eea68ffa163e0fa374'
SERIAL = 'da6fca696db811eea68ffa163e0fa374'


class JavaProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = [e for e in json.loads((ROOT / 'rulesets/catalog.json').read_text())['rules'] if e['id'] in {OVERRIDE, HASHCODE, SERIAL_UID, SYNC, SERIAL}]

    def check_sources(self, files):
        result = scan(files, self.entries)
        self.assertEqual([], result['errors'])
        return result

    def findings(self, result, rule, path):
        return [f for f in result['findings'] if f['id'] == rule and f['path'] == path]

    def test_cross_package_imported_base_and_overload_signatures(self):
        result = self.check_sources([
            ('api/Base.java','package api; public class Base { public void work(int x) {} private void secret() {} public static void stat() {} }'),
            ('app/Bad.java','package app; import api.Base; class Bad extends Base { public void work(int x) {} }'),
            ('app/Good.java','package app; import api.Base; class Good extends Base { @Override public void work(int x) {} void work(String x) {} void secret() {} static void stat() {} }'),
        ])
        self.assertEqual(1,len(self.findings(result,OVERRIDE,'app/Bad.java')))
        self.assertEqual([],self.findings(result,OVERRIDE,'app/Good.java'))

    def test_cross_file_interface_chain_and_generic_substitution(self):
        result = self.check_sources([
            ('api/Consumer.java','package api; public interface Consumer<T> { void accept(T item); }'),
            ('api/StringConsumer.java','package api; public interface StringConsumer extends Consumer<String> {}'),
            ('app/Bad.java','package app; import api.StringConsumer; class Bad implements StringConsumer { public void accept(String item) {} }'),
            ('app/Good.java','package app; import api.StringConsumer; class Good implements StringConsumer { @Override public void accept(String item) {} public void accept(Integer item) {} }'),
        ])
        self.assertEqual(1,len(self.findings(result,OVERRIDE,'app/Bad.java')))
        self.assertEqual([],self.findings(result,OVERRIDE,'app/Good.java'))

    def test_same_simple_name_in_another_package_is_not_inherited(self):
        result = self.check_sources([
            ('one/Base.java','package one; public class Base { public synchronized void work() {} }'),
            ('two/Base.java','package two; public class Base { public void other() {} }'),
            ('app/C.java','package app; import two.Base; class C extends Base { void work() {} }'),
        ])
        self.assertEqual([],self.findings(result,OVERRIDE,'app/C.java'))
        self.assertEqual([],self.findings(result,SYNC,'app/C.java'))

    def test_package_private_method_not_inherited_across_package(self):
        result = self.check_sources([
            ('api/Base.java','package api; public class Base { void local() {} protected void visible() {} }'),
            ('app/C.java','package app; class C extends api.Base { void local() {} protected void visible() {} }'),
        ])
        found=self.findings(result,OVERRIDE,'app/C.java')
        self.assertEqual(1,len(found))
        self.assertEqual('protected void visible', found[0]['evidence'][found[0]['column']-1:][:22])

    def test_serializable_propagates_to_subclasses_and_subinterfaces(self):
        result = self.check_sources([
            ('api/Marker.java','package api; public interface Marker extends java.io.Serializable {}'),
            ('api/Base.java','package api; public class Base implements Marker { private static final long serialVersionUID=1L; }'),
            ('app/Bad.java','package app; class Bad extends api.Base {}'),
            ('app/Good.java','package app; class Good extends api.Base { private static final long serialVersionUID=2L; }'),
        ])
        self.assertEqual(1,len(self.findings(result,SERIAL_UID,'app/Bad.java')))
        self.assertEqual([],self.findings(result,SERIAL_UID,'app/Good.java'))
        self.assertEqual([],self.findings(result,SERIAL_UID,'api/Marker.java'))

    def test_user_defined_serializable_is_not_java_serializable(self):
        result = self.check_sources([
            ('app/Serializable.java','package app; interface Serializable {}'),
            ('app/C.java','package app; class C implements Serializable {}'),
        ])
        self.assertEqual([],self.findings(result,SERIAL_UID,'app/C.java'))

    def test_inherited_real_hashcode_and_user_defined_object(self):
        result = self.check_sources([
            ('api/Base.java','package api; public class Base { @Override public int hashCode() { return 7; } }'),
            ('app/Good.java','package app; class Good extends api.Base { @Override public boolean equals(java.lang.Object other) { return this==other; } }'),
            ('app/Bad.java','package app; class Bad { @Override public boolean equals(java.lang.Object other) { return this==other; } }'),
            ('custom/Object.java','package custom; public class Object {}'),
            ('app/Overload.java','package app; import custom.Object; class Overload { public boolean equals(Object other) { return true; } }'),
        ])
        self.assertEqual([],self.findings(result,HASHCODE,'app/Good.java'))
        self.assertEqual(1,len(self.findings(result,HASHCODE,'app/Bad.java')))
        self.assertEqual([],self.findings(result,HASHCODE,'app/Overload.java'))
        self.assertEqual([],self.findings(result,OVERRIDE,'app/Overload.java'))

    def test_sync_override_checks_exact_cross_file_method_signature(self):
        result = self.check_sources([
            ('api/Base.java','package api; public class Base { public synchronized void work(int value) {} }'),
            ('app/Bad.java','package app; class Bad extends api.Base { @Override public void work(int value) {} }'),
            ('app/Good.java','package app; class Good extends api.Base { @Override public synchronized void work(int value) {} public void work(String value) {} }'),
        ])
        self.assertEqual(1,len(self.findings(result,SYNC,'app/Bad.java')))
        self.assertEqual([],self.findings(result,SYNC,'app/Good.java'))

    def test_unknown_external_parent_has_explicit_type_context(self):
        result = self.check_sources([('app/C.java','package app; import vendor.External; class C extends External { public void work() {} }')])
        self.assertEqual([],self.findings(result,OVERRIDE,'app/C.java'))
        context=result.get('type_context',{})
        self.assertTrue(context.get('unresolved_bases'))
        self.assertEqual('vendor.External',context['unresolved_bases'][0]['type'])

    def test_plain_record_is_not_implicitly_serializable(self):
        values={};original=catalog_java.ProjectSymbols.is_serializable
        def observe(project,symbol):
            result=original(project,symbol)
            values[symbol['name']]=result
            return result
        with patch.object(catalog_java.ProjectSymbols,'is_serializable',observe):
            self.check_sources([
                ('Plain.java','record Plain(int value) {}'),
                ('Persistent.java','record Persistent(int value) implements java.io.Serializable {}'),
            ])
        self.assertFalse(values['Plain'])
        self.assertTrue(values['Persistent'])

    def test_explicit_import_wins_over_same_package_type(self):
        result=self.check_sources([
            ('app/Base.java','package app; public class Base { public void unrelated() {} }'),
            ('api/Base.java','package api; public class Base { public void work() {} }'),
            ('app/C.java','package app; import api.Base; class C extends Base { public void work() {} }'),
        ])
        self.assertEqual(1,len(self.findings(result,OVERRIDE,'app/C.java')))

    def test_java_lang_wildcard_collision_remains_unresolved(self):
        result=self.check_sources([
            ('custom/Object.java','package custom; public class Object {}'),
            ('app/C.java','package app; import custom.*; class C { public boolean equals(Object value) { return true; } }'),
        ])
        # javac rejects ambiguous Object (custom.* and implicit java.lang.*).
        # Parse-only mode must not invent an Object override for it.
        self.assertEqual([],self.findings(result,OVERRIDE,'app/C.java'))
        self.assertEqual([],self.findings(result,HASHCODE,'app/C.java'))
        self.assertTrue(result['type_context'].get('ambiguous_types'))

    def test_return_to_original_package_may_override_package_private_ancestor(self):
        result=self.check_sources([
            ('p/A.java','package p; public class A { synchronized void work() {} }'),
            ('q/B.java','package q; public class B extends p.A {}'),
            ('p/C.java','package p; class C extends q.B { void work() {} }'),
            ('r/D.java','package r; class D extends q.B { void work() {} }'),
        ])
        # Verified against javac: p.C may override p.A despite q.B; r.D may not.
        self.assertEqual(1,len(self.findings(result,OVERRIDE,'p/C.java')))
        self.assertEqual(1,len(self.findings(result,SYNC,'p/C.java')))
        self.assertEqual([],self.findings(result,OVERRIDE,'r/D.java'))
        self.assertEqual([],self.findings(result,SYNC,'r/D.java'))

    def test_static_imported_nested_interface_is_resolved(self):
        result=self.check_sources([
            ('api/Outer.java','package api; public class Outer { public interface Contract { void work(); } }'),
            ('app/C.java','package app; import static api.Outer.Contract; class C implements Contract { public void work() {} }'),
        ])
        self.assertEqual(1,len(self.findings(result,OVERRIDE,'app/C.java')))

    def test_nested_class_is_not_visible_to_unrelated_top_level_class(self):
        result=self.check_sources([
            ('p/Outer.java','package p; class Outer { static class Base { public void work() {} } } class C extends Base { public void work() {} }'),
        ])
        self.assertEqual([],self.findings(result,OVERRIDE,'p/Outer.java'))
        self.assertTrue([base for base in result['type_context']['unresolved_bases'] if base['class']=='p.C' and base['type']=='p.Base'])

    def test_local_class_is_not_visible_to_another_compilation_unit(self):
        result=self.check_sources([
            ('p/Outer.java','package p; class Outer { void f() { class Base { public void work() {} } } }'),
            ('p/C.java','package p; class C extends Outer.Base { public void work() {} }'),
        ])
        self.assertEqual([],self.findings(result,OVERRIDE,'p/C.java'))
        self.assertTrue(result['type_context']['unresolved_bases'])


if __name__=='__main__':unittest.main()
