ThisBuild / scalaVersion := "2.13.10"
ThisBuild / organization := "spec"

lazy val root = (project in file("."))
  .settings(
    name := "rpc-spec-model",
    libraryDependencies ++= Seq(
      "edu.berkeley.cs" %% "chisel3" % "3.6.0",
      // rpc.Replay simulates the Chisel checker from Compile scope, so the
      // simulator is needed outside Test as well.
      "edu.berkeley.cs" %% "chiseltest" % "0.6.2"
    ),
    addCompilerPlugin("edu.berkeley.cs" % "chisel3-plugin" % "3.6.0" cross CrossVersion.full),
    scalacOptions ++= Seq("-deprecation", "-feature", "-unchecked"),
    // Replay reports usage/parse errors through the process exit code.
    Compile / run / fork := true,
    Compile / run / outputStrategy := Some(StdoutOutput),
    Test / parallelExecution := false
  )
