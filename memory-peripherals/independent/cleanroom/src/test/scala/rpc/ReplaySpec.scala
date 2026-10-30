package rpc

import org.scalatest.flatspec.AnyFlatSpec

import java.io.{ByteArrayOutputStream, PrintStream}
import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Path}

class ReplaySpec extends AnyFlatSpec {
  private def runReplay(args: String*): (Int, Seq[String], String) = {
    val out = new ByteArrayOutputStream
    val err = new ByteArrayOutputStream
    val code = Replay.run(args, new PrintStream(out, true, "UTF-8"), new PrintStream(err, true, "UTF-8"))
    val lines = out.toString("UTF-8").split("\n").toSeq.filter(_.nonEmpty)
    (code, lines, err.toString("UTF-8"))
  }

  private def tempJsonl(lines: String*): Path = {
    val f = Files.createTempFile("replay", ".jsonl")
    f.toFile.deleteOnExit()
    Files.write(f, lines.mkString("\n").getBytes(StandardCharsets.UTF_8))
    f
  }

  private val selftest = "spec/selftest.jsonl"
  private val common = Seq(
    "ACCEPT cycle=160000 op=RESET",
    "ACCEPT cycle=164000 op=PRE",
    "ACCEPT cycle=164011 op=MRS",
    "ACCEPT cycle=164023 op=ZQ",
    "ACCEPT cycle=165623 op=ACT"
  )

  "spec/selftest.jsonl" should "match the Packet encoders" in {
    val expected = Seq(
      Packet.reset, Packet.preAll, Packet.mrs(11), Packet.zq(0), Packet.act(0, 0x2a),
      Packet.rd(0, 5), Packet.rd(0, 5), Packet.wr(0, 6), Packet.pre(1), Packet.pre(1),
      Packet.ref(1), Packet.act(1, 0x100)
    )
    val lines = Files.readAllLines(java.nio.file.Paths.get(selftest)).toArray(Array.empty[String]).toSeq
    assert(Replay.parseRecords(lines).map(_.packet) == expected)
  }

  "Replay" should "report legal and early commands at tCK 1250 ps with refresh-select 0" in {
    val (code, lines, _) = runReplay("--tck-ps", "1250", "--refresh-select", "0", selftest)
    assert(code == 0)
    assert(lines == common ++ Seq(
      "VIOLATION constraint=TRCD offered=165631 earliest=165639 op=RD",
      "ACCEPT cycle=165639 op=RD",
      "ACCEPT cycle=165671 op=WR",
      "VIOLATION constraint=TBESL_WRITE offered=165703 earliest=165711 op=PRE",
      "ACCEPT cycle=165711 op=PRE",
      "ACCEPT cycle=165722 op=REF",
      "INTERPRETATION constraint=REFRESH_BUSY offered=493646 earliest=565966 op=ACT " +
        "detail=refresh-completion-not-specified;rs1-earliest=493646;rs2-earliest=565966;" +
        "state-updated-as-if-refresh-complete"
    ))
  }

  it should "collapse the refresh reading for refresh-select 1 and 2" in {
    val (c1, l1, _) = runReplay("--tck-ps", "1250", "--refresh-select", "1", selftest)
    assert(c1 == 0 && l1.last == "ACCEPT cycle=493646 op=ACT")
    val (c2, l2, _) = runReplay("--tck-ps", "1250", "--refresh-select", "2", selftest)
    assert(c2 == 0 && l2.last == "VIOLATION constraint=REFRESH_BUSY offered=493646 earliest=565966 op=ACT")
  }

  it should "convert the same cycles at tCK 2500 ps" in {
    val (code, lines, _) = runReplay("--tck-ps", "2500", "--refresh-select", "0", selftest)
    assert(code == 0)
    assert(lines == common ++ Seq(
      "ACCEPT cycle=165631 op=RD",
      "VIOLATION constraint=TBESL_READ offered=165639 earliest=165663 op=RD",
      "ACCEPT cycle=165671 op=WR",
      "VIOLATION constraint=TBESL_WRITE offered=165703 earliest=165711 op=PRE",
      "ACCEPT cycle=165711 op=PRE",
      "ACCEPT cycle=165722 op=REF",
      "ACCEPT cycle=493646 op=ACT"
    ))
  }

  it should "print na when no wait makes the command legal, and ignore extra fields and blank lines" in {
    val f = tempJsonl(
      """{"cycle": 5, "packet_hex": "a000", "comment": {"x": [1, 2.5, true, null]}}""",
      "",
      """{"packet_hex": "1", "cycle": 6}""",
      """{"cycle": 7, "packet_hex": "00010002"}"""
    )
    val (code, lines, _) = runReplay("--tck-ps", "1250", "--refresh-select", "0", f.toString)
    assert(code == 0)
    assert(lines == Seq(
      "VIOLATION constraint=INIT_RESET_REQUIRED offered=5 earliest=na op=RD",
      "VIOLATION constraint=INIT_RESET_REQUIRED offered=6 earliest=na op=WR",
      "VIOLATION constraint=INIT_RESET_REQUIRED offered=7 earliest=na op=PD_ENTRY"
    ))
  }

  it should "accept every tCK(avg) row and refresh-select value" in {
    val f = tempJsonl("""{"cycle": 200000, "packet_hex": "00010000"}""")
    for (op <- RpcConfig.operatingPoints; rs <- 0 to 2) {
      val (code, lines, _) = runReplay("--tck-ps", op.tckPs.toString, "--refresh-select", rs.toString, f.toString)
      assert(code == 0 && lines == Seq("ACCEPT cycle=200000 op=RESET"), s"tCK=${op.tckPs} rs=$rs")
    }
  }

  it should "exit 2 on usage errors" in {
    val f = tempJsonl("""{"cycle": 1, "packet_hex": "0"}""")
    val bad = Seq(
      Seq(),
      Seq("--tck-ps", "1250", f.toString),
      Seq("--refresh-select", "0", f.toString),
      Seq("--tck-ps", "1250", "--refresh-select", "0"),
      Seq("--tck-ps", "1000", "--refresh-select", "0", f.toString),
      Seq("--tck-ps", "abc", "--refresh-select", "0", f.toString),
      Seq("--tck-ps", "1250", "--refresh-select", "3", f.toString),
      Seq("--tck-ps", "1250", "--refresh-select", "0", "--bogus", f.toString),
      Seq("--tck-ps", "1250", "--refresh-select", "0", f.toString, f.toString),
      Seq("--tck-ps", "1250", "--refresh-select")
    )
    for (a <- bad) {
      val (code, lines, err) = runReplay(a: _*)
      assert(code == 2 && lines.isEmpty && err.contains("usage:"), a.mkString(" "))
    }
  }

  it should "exit 3 on unreadable or malformed input without printing partial results" in {
    val bad = Seq(
      Seq("""{"cycle": 1, "packet_hex": "0"}""", """{"cycle": 2, "packet_hex": "0x10"}"""),
      Seq("""{"cycle": -1, "packet_hex": "0"}"""),
      Seq("""{"cycle": 1.5, "packet_hex": "0"}"""),
      Seq("""{"cycle": "1", "packet_hex": "0"}"""),
      Seq("""{"cycle": 18446744073709551616, "packet_hex": "0"}"""),
      Seq("""{"cycle": 1, "packet_hex": "123456789"}"""),
      Seq("""{"cycle": 1}"""),
      Seq("""{"packet_hex": "0"}"""),
      Seq("""[1, 2]"""),
      Seq("""{"cycle": 1, "packet_hex": "0"} trailing"""),
      Seq("""{"cycle": 1, "packet_hex": "0""")
    )
    for (content <- bad) {
      val f = tempJsonl(content: _*)
      val (code, lines, err) = runReplay("--tck-ps", "1250", "--refresh-select", "0", f.toString)
      assert(code == 3 && lines.isEmpty && err.contains("line"), content.mkString(" | "))
    }
    val (code, _, _) = runReplay("--tck-ps", "1250", "--refresh-select", "0", "no/such/file.jsonl")
    assert(code == 3)
  }

  it should "accept the largest 64-bit cycle" in {
    val f = tempJsonl("""{"cycle": 18446744073709551615, "packet_hex": "00010000"}""")
    val (code, lines, _) = runReplay("--tck-ps", "1250", "--refresh-select", "0", f.toString)
    assert(code == 0 && lines == Seq("ACCEPT cycle=18446744073709551615 op=RESET"))
  }
}
