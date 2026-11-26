"""Generate the Kali Code iOS Xcode project.

An Xcode project is a `project.pbxproj` file - a plist with stable 24-hex
object ids. Writing it by hand is error prone, so this script generates it
from the source files that are actually present.

Usage:
    python tools/build_ios_project.py
    python tools/build_ios_project.py --open     # also open it in Xcode
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IOS = ROOT / "ios"
PROJECT = IOS / "KaliCode.xcodeproj"

APP_SOURCES = [
    "Sources/KaliCode/KaliApp.swift",
]

KIT_SOURCES = [
    "Sources/KaliCodeKit/Protocol.swift",
    "Sources/KaliCodeKit/KaliClient.swift",
    "Sources/KaliCodeKit/KaliStore.swift",
    "Sources/KaliCodeKit/Theme.swift",
]

RESOURCES = [
    "Resources/Info.plist",
    "Resources/KaliCode.entitlements",
    "Resources/Assets.xcassets",
]

BUNDLE_ID = "com.kalicode.app"
TEAM = ""  # set this to your Apple Developer team id


def oid(seed: str) -> str:
    """A stable 24-hex-digit object id for a name."""
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:24].upper()


def file_type(path: str) -> str:
    if path.endswith(".swift"):
        return "sourcecode.swift"
    if path.endswith(".plist"):
        return "text.plist.xml"
    if path.endswith(".entitlements"):
        return "text.plist.entitlements"
    if path.endswith(".xcassets"):
        return "folder.assetcatalog"
    if path.endswith(".json"):
        return "text.json"
    if path.endswith(".md"):
        return "net.daringfireball.markdown"
    return "text"


class Ref:
    """A file reference."""

    def __init__(self, path: str, tree: str = "<group>"):
        self.path = path
        self.tree = tree
        self.name = Path(path).name
        self.id = oid("file:" + path)
        self.child = oid("child:" + path)


def build() -> str:
    app_files = [Ref(p) for p in APP_SOURCES]
    kit_files = [Ref(p) for p in KIT_SOURCES]
    res_files = [Ref(p) for p in RESOURCES]
    all_files = app_files + kit_files + res_files

    product = Ref("KaliCode.app")
    product.id = oid("product:KaliCode")

    # ---- groups
    group_ids = {
        "Sources": oid("group:Sources"),
        "KaliCode": oid("group:Sources/KaliCode"),
        "KaliCodeKit": oid("group:Sources/KaliCodeKit"),
        "Resources": oid("group:Resources"),
        "Products": oid("group:Products"),
        "root": oid("group:root"),
    }

    lines: list[str] = []
    add = lines.append

    add("// !$*UTF8*$!")
    add("{")
    add("\tarchiveVersion = 1;")
    add("\tclasses = {")
    add("\t};")
    add("\tobjectVersion = 56;")
    add("\tobjects = {")

    # ---- PBXBuildFile
    add("")
    add("/* Begin PBXBuildFile section */")
    for f in all_files:
        if f.path.endswith(".plist") or f.path.endswith(".entitlements"):
            continue
        add(f"\t\t{f.child} /* {f.name} in Frameworks */ = "
            f"{{isa = PBXBuildFile; fileRef = {f.id} /* {f.name} */; }};")
    add("/* End PBXBuildFile section */")

    # ---- PBXFileReference
    add("")
    add("/* Begin PBXFileReference section */")
    for f in all_files:
        add(f"\t\t{f.id} /* {f.name} */ = {{isa = PBXFileReference; "
            f"lastKnownFileType = {file_type(f.path)}; path = {f.name}; "
            f"sourceTree = \"<group>\"; }};")
    add(f"\t\t{product.id} /* KaliCode.app */ = {{isa = PBXFileReference; "
        f"explicitFileType = wrapper.application; includeInIndex = 0; "
        f"path = KaliCode.app; sourceTree = BUILT_PRODUCTS_DIR; }};")
    add("/* End PBXFileReference section */")

    # ---- PBXFrameworksBuildPhase
    add("")
    add("/* Begin PBXFrameworksBuildPhase section */")
    add(f"\t\t{oid('phase:frameworks')} /* Frameworks */ = {{")
    add("\t\t\tisa = PBXFrameworksBuildPhase;")
    add("\t\t\tbuildActionMask = 2147483647;")
    add("\t\t\tfiles = (")
    for f in all_files:
        if f.path.endswith(".plist") or f.path.endswith(".entitlements"):
            continue
        add(f"\t\t\t\t{f.child} /* {f.name} in Frameworks */,")
    add("\t\t\t);")
    add("\t\t\trunOnlyForDeploymentPostprocessing = 0;")
    add("\t\t};")
    add("/* End PBXFrameworksBuildPhase section */")

    # ---- PBXGroup
    add("")
    add("/* Begin PBXGroup section */")
    add(f"\t\t{group_ids['root']} = {{")
    add("\t\t\tisa = PBXGroup;")
    add("\t\t\tchildren = (")
    add(f"\t\t\t\t{group_ids['Sources']} /* Sources */,")
    add(f"\t\t\t\t{group_ids['Resources']} /* Resources */,")
    add(f"\t\t\t\t{group_ids['Products']} /* Products */,")
    add("\t\t\t);")
    add("\t\t\tsourceTree = \"<group>\";")
    add("\t\t};")

    add(f"\t\t{group_ids['Sources']} /* Sources */ = {{")
    add("\t\t\tisa = PBXGroup;")
    add("\t\t\tchildren = (")
    add(f"\t\t\t\t{group_ids['KaliCode']} /* KaliCode */,")
    add(f"\t\t\t\t{group_ids['KaliCodeKit']} /* KaliCodeKit */,")
    add("\t\t\t);")
    add("\t\t\tpath = Sources;")
    add("\t\t\tsourceTree = \"<group>\";")
    add("\t\t};")

    for key, label, files in (
        ("KaliCode", "KaliCode", app_files),
        ("KaliCodeKit", "KaliCodeKit", kit_files),
    ):
        add(f"\t\t{group_ids[key]} /* {label} */ = {{")
        add("\t\t\tisa = PBXGroup;")
        add("\t\t\tchildren = (")
        for f in files:
            add(f"\t\t\t\t{f.id} /* {f.name} */,")
        add("\t\t\t);")
        add(f"\t\t\tpath = {label};")
        add("\t\t\tsourceTree = \"<group>\";")
        add("\t\t};")

    add(f"\t\t{group_ids['Resources']} /* Resources */ = {{")
    add("\t\t\tisa = PBXGroup;")
    add("\t\t\tchildren = (")
    for f in res_files:
        add(f"\t\t\t\t{f.id} /* {f.name} */,")
    add("\t\t\t);")
    add("\t\t\tpath = Resources;")
    add("\t\t\tsourceTree = \"<group>\";")
    add("\t\t};")

    add(f"\t\t{group_ids['Products']} /* Products */ = {{")
    add("\t\t\tisa = PBXGroup;")
    add("\t\t\tchildren = (")
    add(f"\t\t\t\t{product.id} /* KaliCode.app */,")
    add("\t\t\t);")
    add("\t\t\tname = Products;")
    add("\t\t\tsourceTree = \"<group>\";")
    add("\t\t};")
    add("/* End PBXGroup section */")

    # ---- PBXNativeTarget
    add("")
    add("/* Begin PBXNativeTarget section */")
    add(f"\t\t{oid('target:app')} /* KaliCode */ = {{")
    add("\t\t\tisa = PBXNativeTarget;")
    add(f"\t\t\tbuildConfigurationList = "
        f"{oid('configlist:target')} /* Build configuration list */;")
    add("\t\t\tbuildPhases = (")
    add(f"\t\t\t\t{oid('phase:sources')} /* Sources */,")
    add(f"\t\t\t\t{oid('phase:frameworks')} /* Frameworks */,")
    add(f"\t\t\t\t{oid('phase:resources')} /* Resources */,")
    add("\t\t\t);")
    add("\t\t\tbuildRules = (")
    add("\t\t\t);")
    add("\t\t\tdependencies = (")
    add("\t\t\t);")
    add("\t\t\tname = KaliCode;")
    add("\t\t\tproductName = KaliCode;")
    add(f"\t\t\tproductReference = {product.id} /* KaliCode.app */;")
    add("\t\t\tproductType = \"com.apple.product-type.application\";")
    add("\t\t};")
    add("/* End PBXNativeTarget section */")

    # ---- PBXProject
    add("")
    add("/* Begin PBXProject section */")
    add(f"\t\t{oid('project')} /* Project object */ = {{")
    add("\t\t\tisa = PBXProject;")
    add("\t\t\tattributes = {")
    add("\t\t\t\tBuildIndependentTargetsInParallel = 1;")
    add("\t\t\t\tLastSwiftUpdateCheck = 1600;")
    add("\t\t\t\tLastUpgradeCheck = 1600;")
    add("\t\t\t\tTargetAttributes = {")
    add(f"\t\t\t\t\t{oid('target:app')} = {{")
    add("\t\t\t\t\t\tCreatedOnToolsVersion = 16.0;")
    add("\t\t\t\t\t};")
    add("\t\t\t\t};")
    add("\t\t\t};")
    add(f"\t\t\tbuildConfigurationList = "
        f"{oid('configlist:project')} /* Build configuration list */;")
    add("\t\t\tcompatibilityVersion = \"Xcode 15.0\";")
    add("\t\t\tdevelopmentRegion = en;")
    add("\t\t\thasScannedForEncodings = 0;")
    add("\t\t\tknownRegions = (")
    add("\t\t\t\ten,")
    add("\t\t\t\tBase,")
    add("\t\t\t);")
    add(f"\t\t\tmainGroup = {group_ids['root']};")
    add(f"\t\t\tproductRefGroup = {group_ids['Products']} /* Products */;")
    add("\t\t\tprojectDirPath = \"\";")
    add("\t\t\tprojectRoot = \"\";")
    add("\t\t\ttargets = (")
    add(f"\t\t\t\t{oid('target:app')} /* KaliCode */,")
    add("\t\t\t);")
    add("\t\t};")
    add("/* End PBXProject section */")

    # ---- PBXResourcesBuildPhase
    add("")
    add("/* Begin PBXResourcesBuildPhase section */")
    add(f"\t\t{oid('phase:resources')} /* Resources */ = {{")
    add("\t\t\tisa = PBXResourcesBuildPhase;")
    add("\t\t\tbuildActionMask = 2147483647;")
    add("\t\t\tfiles = (")
    for f in res_files:
        if f.path.endswith(".plist") or f.path.endswith(".entitlements"):
            continue
        add(f"\t\t\t\t{f.child} /* {f.name} in Resources */,")
    add("\t\t\t);")
    add("\t\t\trunOnlyForDeploymentPostprocessing = 0;")
    add("\t\t};")
    add("/* End PBXResourcesBuildPhase section */")

    # ---- PBXSourcesBuildPhase
    add("")
    add("/* Begin PBXSourcesBuildPhase section */")
    add(f"\t\t{oid('phase:sources')} /* Sources */ = {{")
    add("\t\t\tisa = PBXSourcesBuildPhase;")
    add("\t\t\tbuildActionMask = 2147483647;")
    add("\t\t\tfiles = (")
    for f in app_files + kit_files:
        add(f"\t\t\t\t{f.child} /* {f.name} in Sources */,")
    add("\t\t\t);")
    add("\t\t\trunOnlyForDeploymentPostprocessing = 0;")
    add("\t\t};")
    add("/* End PBXSourcesBuildPhase section */")

    # ---- XCBuildConfiguration
    add("")
    add("/* Begin XCBuildConfiguration section */")

    def config(key: str, name: str, settings: dict[str, str],
               comment: str) -> None:
        add(f"\t\t{oid('config:' + key)} /* {name} */ = {{")
        add("\t\t\tisa = XCBuildConfiguration;")
        add("\t\t\tbuildSettings = {")
        for k, v in settings.items():
            add(f"\t\t\t\t{k} = {v};")
        add("\t\t\t};")
        add(f"\t\t\tname = {name};")
        add("\t\t};")

    project_common = {
        "ALWAYS_SEARCH_USER_PATHS": "NO",
        "CLANG_ENABLE_MODULES": "YES",
        "CLANG_ENABLE_OBJC_ARC": "YES",
        "ENABLE_STRICT_OBJC_MSGSEND": "YES",
        "GCC_C_LANGUAGE_STANDARD": "gnu17",
        "IPHONEOS_DEPLOYMENT_TARGET": "16.0",
        "SDKROOT": "iphoneos",
        "SWIFT_VERSION": "5.9",
    }
    config("project-debug", "Debug", dict(project_common, **{
        "DEBUG_INFORMATION_FORMAT": "dwarf",
        "ENABLE_TESTABILITY": "YES",
        "GCC_OPTIMIZATION_LEVEL": "0",
        "ONLY_ACTIVE_ARCH": "YES",
        "SWIFT_ACTIVE_COMPILATION_CONDITIONS": "DEBUG",
        "SWIFT_OPTIMIZATION_LEVEL": "\"-Onone\"",
    }), "Debug")

    config("project-release", "Release", dict(project_common, **{
        "DEBUG_INFORMATION_FORMAT": "\"dwarf-with-dsym\"",
        "ENABLE_NS_ASSERTIONS": "NO",
        "SWIFT_COMPILATION_MODE": "wholemodule",
        "VALIDATE_PRODUCT": "YES",
    }), "Release")

    target_settings = {
        "ASSETCATALOG_COMPILER_APPICON_NAME": "AppIcon",
        "CODE_SIGN_ENTITLEMENTS": "Resources/KaliCode.entitlements",
        "CODE_SIGN_STYLE": "Automatic",
        "CURRENT_PROJECT_VERSION": "1",
        "ENABLE_PREVIEWS": "YES",
        "GENERATE_INFOPLIST_FILE": "NO",
        "INFOPLIST_FILE": "Resources/Info.plist",
        "INFOPLIST_KEY_UILaunchScreen_Generation": "YES",
        "IPHONEOS_DEPLOYMENT_TARGET": "16.0",
        "LD_RUNPATH_SEARCH_PATHS": "(\n\t\t\t\t\t\"$(inherited)\",\n"
                                   "\t\t\t\t\t\"@executable_path/Frameworks\",\n\t\t\t\t)",
        "MARKETING_VERSION": "1.2.0",
        "PRODUCT_BUNDLE_IDENTIFIER": BUNDLE_ID,
        "PRODUCT_NAME": "\"$(TARGET_NAME)\"",
        "SWIFT_EMIT_LOC_STRINGS": "YES",
        "TARGETED_DEVICE_FAMILY": "\"1,2\"",
    }
    if TEAM:
        target_settings["DEVELOPMENT_TEAM"] = TEAM
        target_settings["CODE_SIGN_IDENTITY"] = "\"Apple Development\""

    config("target-debug", "Debug", dict(target_settings), "Debug")
    config("target-release", "Release", dict(target_settings), "Release")
    add("/* End XCBuildConfiguration section */")

    # ---- XCConfigurationList
    add("")
    add("/* Begin XCConfigurationList section */")
    for key, comment in (("project", "PBXProject"),
                         ("target", "PBXNativeTarget")):
        add(f"\t\t{oid('configlist:' + key)} /* Build configuration list "
            f"for {comment} */ = {{")
        add("\t\t\tisa = XCConfigurationList;")
        add("\t\t\tbuildConfigurations = (")
        add(f"\t\t\t\t{oid('config:' + key + '-debug')} /* Debug */,")
        add(f"\t\t\t\t{oid('config:' + key + '-release')} /* Release */,")
        add("\t\t\t);")
        add("\t\t\tdefaultConfigurationIsVisible = 0;")
        add("\t\t\tdefaultConfigurationName = Release;")
        add("\t\t};")
    add("/* End XCConfigurationList section */")

    add("\t};")
    add(f"\trootObject = {oid('project')} /* Project object */;")
    add("}")

    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate the iOS Xcode project")
    ap.add_argument("--open", action="store_true",
                    help="open the project in Xcode afterwards")
    args = ap.parse_args()

    PROJECT.mkdir(parents=True, exist_ok=True)
    pbx = PROJECT / "project.pbxproj"
    pbx.write_text(build(), encoding="utf-8")

    # A shared scheme, so the project is runnable straight away.
    scheme_dir = PROJECT / "xcshareddata" / "xcschemes"
    scheme_dir.mkdir(parents=True, exist_ok=True)
    (scheme_dir / "KaliCode.xcscheme").write_text(
        SCHEME.replace("PLACEHOLDER_TARGET", oid("target:app")),
        encoding="utf-8")

    print(f"wrote {pbx}")
    print(f"wrote {scheme_dir / 'KaliCode.xcscheme'}")

    if args.open and sys.platform == "darwin":
        subprocess.run(["open", str(PROJECT)], check=False)
    return 0


SCHEME = """<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion = "1600" version = "1.7">
   <BuildAction parallelizeBuildables = "YES" buildImplicitDependencies = "YES">
      <BuildActionEntries>
         <BuildActionEntry buildForTesting = "YES" buildForRunning = "YES"
                           buildForProfiling = "YES" buildForArchiving = "YES"
                           buildForAnalyzing = "YES">
            <BuildableReference
               BuildableIdentifier = "primary"
               BlueprintIdentifier = "PLACEHOLDER_TARGET"
               BuildableName = "KaliCode.app"
               BlueprintName = "KaliCode"
               ReferencedContainer = "container:KaliCode.xcodeproj">
            </BuildableReference>
         </BuildActionEntry>
      </BuildActionEntries>
   </BuildAction>
   <TestAction buildConfiguration = "Debug" selectedDebuggerIdentifier =
      "Xcode.DebuggerFoundation.Debugger.LLDB"
      selectedLauncherIdentifier = "Xcode.DebuggerFoundation.Launcher.LLDB"
      shouldUseLaunchSchemeArgsEnv = "YES">
      <Testables>
      </Testables>
   </TestAction>
   <LaunchAction buildConfiguration = "Debug" selectedDebuggerIdentifier =
      "Xcode.DebuggerFoundation.Debugger.LLDB"
      selectedLauncherIdentifier = "Xcode.DebuggerFoundation.Launcher.LLDB"
      launchStyle = "0" useCustomWorkingDirectory = "NO"
      ignoresPersistentStateOnLaunch = "NO" debugDocumentVersioning = "YES"
      debugServiceExtension = "internal" allowLocationSimulation = "YES">
      <BuildableProductRunnable runnableDebuggingMode = "0">
         <BuildableReference
            BuildableIdentifier = "primary"
            BlueprintIdentifier = "PLACEHOLDER_TARGET"
            BuildableName = "KaliCode.app"
            BlueprintName = "KaliCode"
            ReferencedContainer = "container:KaliCode.xcodeproj">
         </BuildableReference>
      </BuildableProductRunnable>
   </LaunchAction>
   <ProfileAction buildConfiguration = "Release" shouldUseLaunchSchemeArgsEnv =
      "YES" savedToolIdentifier = "" useCustomWorkingDirectory = "NO"
      debugDocumentVersioning = "YES">
      <BuildableProductRunnable runnableDebuggingMode = "0">
         <BuildableReference
            BuildableIdentifier = "primary"
            BlueprintIdentifier = "PLACEHOLDER_TARGET"
            BuildableName = "KaliCode.app"
            BlueprintName = "KaliCode"
            ReferencedContainer = "container:KaliCode.xcodeproj">
         </BuildableReference>
      </BuildableProductRunnable>
   </ProfileAction>
   <AnalyzeAction buildConfiguration = "Debug">
   </AnalyzeAction>
   <ArchiveAction buildConfiguration = "Release" revealArchiveInOrganizer = "YES">
   </ArchiveAction>
</Scheme>
"""


if __name__ == "__main__":
    sys.exit(main())
