package rpc

import chisel3._
import chiseltest._

import java.io.{OutputStream, PrintStream}
import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Paths}
import scala.jdk.CollectionConverters._

/** Minimal JSON reader: enough to read one object per JSONL line. */
object MiniJson {
  sealed trait Value
  case class Obj(fields: Map[String, Value]) extends Value
  case class Arr(items: Seq[Value]) extends Value
  case class Str(s: String) extends Value
  case class Num(text: String) extends Value
  case class JBool(b: Boolean) extends Value
  case object Null extends Value

  class ParseError(msg: String) extends Exception(msg)

  def parse(text: String): Value = {
    val p = new Parser(text)
    val v = p.value()
    p.ws()
    if (!p.atEnd) p.fail("trailing characters")
    v
  }

  private class Parser(s: String) {
    private var i = 0
    def atEnd: Boolean = i >= s.length
    def fail(msg: String): Nothing = throw new ParseError(s"$msg at column ${i + 1}")
    def ws(): Unit = while (!atEnd && " \t\r\n".indexOf(s(i)) >= 0) i += 1
    private def expect(c: Char): Unit = {
      if (atEnd || s(i) != c) fail(s"expected '$c'")
      i += 1
    }
    private def literal(word: String, v: Value): Value = {
      if (!s.startsWith(word, i)) fail("invalid literal")
      i += word.length
      v
    }
    def value(): Value = {
      ws()
      if (atEnd) fail("unexpected end of input")
      s(i) match {
        case '{' => obj()
        case '[' => arr()
        case '"' => Str(str())
        case 't' => literal("true", JBool(true))
        case 'f' => literal("false", JBool(false))
        case 'n' => literal("null", Null)
        case c if c == '-' || c.isDigit => num()
        case _ => fail("unexpected character")
      }
    }
    private def obj(): Value = {
      expect('{')
      val fields = scala.collection.mutable.LinkedHashMap[String, Value]()
      ws()
      if (!atEnd && s(i) == '}') { i += 1; return Obj(fields.toMap) }
      var more = true
      while (more) {
        ws()
        val k = str()
        ws()
        expect(':')
        fields(k) = value()
        ws()
        if (!atEnd && s(i) == ',') i += 1 else more = false
      }
      ws()
      expect('}')
      Obj(fields.toMap)
    }
    private def arr(): Value = {
      expect('[')
      val items = scala.collection.mutable.ArrayBuffer[Value]()
      ws()
      if (!atEnd && s(i) == ']') { i += 1; return Arr(items.toSeq) }
      var more = true
      while (more) {
        items += value()
        ws()
        if (!atEnd && s(i) == ',') i += 1 else more = false
      }
      ws()
      expect(']')
      Arr(items.toSeq)
    }
    private def str(): String = {
      expect('"')
      val sb = new StringBuilder
      while (!atEnd && s(i) != '"') {
        val c = s(i)
        if (c == '\\') {
          i += 1
          if (atEnd) fail("bad escape")
          s(i) match {
            case '"' => sb += '"'
            case '\\' => sb += '\\'
            case '/' => sb += '/'
            case 'b' => sb += '\b'
            case 'f' => sb += '\f'
            case 'n' => sb += '\n'
            case 'r' => sb += '\r'
            case 't' => sb += '\t'
            case 'u' =>
              if (i + 4 >= s.length) fail("bad unicode escape")
              sb += Integer.parseInt(s.substring(i + 1, i + 5), 16).toChar
              i += 4
            case _ => fail("bad escape")
          }
        } else sb += c
        i += 1
      }
      expect('"')
      sb.toString
    }
    private def num(): Value = {
      val start = i
      if (s(i) == '-') i += 1
      while (!atEnd && (s(i).isDigit || ".eE+-".indexOf(s(i)) >= 0)) i += 1
      val t = s.substring(start, i)
      if (!t.matches("""-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?""")) fail("bad number")
      Num(t)
    }
  }
}

object Replay {
  case class Record(lineNo: Int, cycle: BigInt, packet: Long)

  case class Outcome(
      kind: Int,
      constraintId: Int,
      earliest: BigInt,
      opCode: Int,
      earliestRs1: BigInt,
      earliestRs2: BigInt
  )

  class UsageError(msg: String) extends Exception(msg)
  class InputError(msg: String) extends Exception(msg)

  val usage: String =
    "usage: rpc.Replay --tck-ps <picoseconds> --refresh-select <0|1|2> <file.jsonl>"

  private val maxCycle = (BigInt(1) << 64) - 1

  def parseRecords(lines: Seq[String]): Seq[Record] =
    lines.zipWithIndex.flatMap { case (raw, idx) =>
      val lineNo = idx + 1
      if (raw.trim.isEmpty) None
      else {
        def bad(msg: String) = throw new InputError(s"line $lineNo: $msg")
        val fields = (try MiniJson.parse(raw)
                      catch { case e: MiniJson.ParseError => bad(e.getMessage) }) match {
          case MiniJson.Obj(f) => f
          case _ => bad("expected a JSON object")
        }
        val cycle = fields.get("cycle") match {
          case Some(MiniJson.Num(t)) if t.matches("""0|[1-9]\d*""") =>
            val v = BigInt(t)
            if (v > maxCycle) bad("cycle does not fit in 64 bits")
            v
          case Some(_) => bad("cycle must be a non-negative integer")
          case None => bad("missing cycle")
        }
        val packet = fields.get("packet_hex") match {
          case Some(MiniJson.Str(h)) if h.matches("[0-9a-fA-F]{1,8}") => java.lang.Long.parseLong(h, 16)
          case Some(_) => bad("packet_hex must be 1 to 8 hexadecimal digits without a prefix")
          case None => bad("missing packet_hex")
        }
        Some(Record(lineNo, cycle, packet))
      }
    }

  /** Runs the records through RpcTimingChecker and returns what was peeked. */
  def simulate(tckPs: Int, refreshSelect: Int, records: Seq[Record]): Seq[Outcome] = {
    val outcomes = scala.collection.mutable.ArrayBuffer[Outcome]()
    quietly {
      RawTester.test(new RpcTimingChecker(), testName = "rpc_replay") { dut =>
        dut.io.tckPs.poke(tckPs.U)
        dut.io.refreshSelect.poke(refreshSelect.U)
        dut.io.valid.poke(false.B)
        for (r <- records) {
          dut.io.valid.poke(true.B)
          dut.io.cycle.poke(r.cycle.U(64.W))
          dut.io.packet.poke(r.packet.U(32.W))
          outcomes += Outcome(
            dut.io.kind.peek().litValue.toInt,
            dut.io.constraintId.peek().litValue.toInt,
            dut.io.earliest.peek().litValue,
            dut.io.opCode.peek().litValue.toInt,
            dut.io.earliestRs1.peek().litValue,
            dut.io.earliestRs2.peek().litValue
          )
          dut.clock.step()
        }
        dut.io.valid.poke(false.B)
      }
    }
    outcomes.toSeq
  }

  def format(r: Record, o: Outcome): String = {
    val op = Op.name(o.opCode)
    val c = Constraint.name(o.constraintId)
    val e = if (o.earliest == 0) "na" else o.earliest.toString
    o.kind match {
      case Kind.ACCEPT => s"ACCEPT cycle=${r.cycle} op=$op"
      case Kind.VIOLATION => s"VIOLATION constraint=$c offered=${r.cycle} earliest=$e op=$op"
      case Kind.INTERPRETATION =>
        val detail = o.constraintId match {
          case Constraint.REFRESH_BUSY =>
            s"refresh-completion-not-specified;rs1-earliest=${o.earliestRs1};rs2-earliest=${o.earliestRs2}" +
              ";state-updated-as-if-refresh-complete"
          case Constraint.UNMODELED_POWER_DOWN =>
            "power-down-not-modeled;exit-is-signalled-on-CS#-outside-the-packet-stream;state-not-updated"
          case _ => "interpretation"
        }
        s"INTERPRETATION constraint=$c offered=${r.cycle} earliest=$e op=$op detail=$detail"
      case k => throw new IllegalStateException(s"checker returned kind $k for a valid command")
    }
  }

  case class Args(tckPs: Int, refreshSelect: Int, file: String)

  def parseArgs(args: Seq[String]): Args = {
    var tck: Option[Int] = None
    var rs: Option[Int] = None
    var file: Option[String] = None
    def int(flag: String, v: String): Int =
      try v.toInt
      catch { case _: NumberFormatException => throw new UsageError(s"$flag expects an integer, got '$v'") }
    var rest = args.toList
    while (rest.nonEmpty) {
      rest match {
        case "--tck-ps" :: v :: tail => tck = Some(int("--tck-ps", v)); rest = tail
        case "--refresh-select" :: v :: tail => rs = Some(int("--refresh-select", v)); rest = tail
        case ("--tck-ps" | "--refresh-select") :: Nil => throw new UsageError(s"${rest.head} needs a value")
        case f :: _ if f.startsWith("--") => throw new UsageError(s"unknown option $f")
        case f :: tail =>
          if (file.nonEmpty) throw new UsageError("exactly one input file is expected")
          file = Some(f); rest = tail
        case Nil =>
      }
    }
    val a = Args(
      tck.getOrElse(throw new UsageError("--tck-ps is required")),
      rs.getOrElse(throw new UsageError("--refresh-select is required")),
      file.getOrElse(throw new UsageError("an input file is required"))
    )
    if (!RpcConfig.validTck(a.tckPs))
      throw new UsageError(
        s"--tck-ps ${a.tckPs} is outside the datasheet range (tCK(avg) min 1250 ps; the checker input is 16 bits)")
    if (!RpcConfig.refreshReadings.exists(_._1 == a.refreshSelect))
      throw new UsageError(s"--refresh-select must be one of ${RpcConfig.refreshReadings.map(_._1).mkString(", ")}")
    a
  }

  /** Returns the process exit code. */
  def run(args: Seq[String], out: PrintStream, err: PrintStream): Int =
    try {
      val a = parseArgs(args)
      val path = Paths.get(a.file)
      if (!Files.isRegularFile(path)) throw new InputError(s"cannot read ${a.file}")
      val records = parseRecords(Files.readAllLines(path, StandardCharsets.UTF_8).asScala.toSeq)
      val outcomes = simulate(a.tckPs, a.refreshSelect, records)
      records.zip(outcomes).foreach { case (r, o) => out.println(format(r, o)) }
      out.flush()
      0
    } catch {
      case e: UsageError =>
        err.println(s"error: ${e.getMessage}")
        err.println(usage)
        2
      case e: InputError =>
        err.println(s"error: ${e.getMessage}")
        3
    }

  def main(args: Array[String]): Unit = sys.exit(run(args.toSeq, System.out, System.err))

  /** Keeps simulator and elaboration chatter off stdout. */
  private def quietly[T](body: => T): T = {
    val sink = new PrintStream(OutputStream.nullOutputStream())
    val (oldOut, oldErr) = (System.out, System.err)
    System.setOut(sink)
    System.setErr(sink)
    try Console.withOut(sink)(Console.withErr(sink)(body))
    finally {
      System.setOut(oldOut)
      System.setErr(oldErr)
    }
  }
}
